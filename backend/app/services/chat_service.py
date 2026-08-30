"""
Orchestrates a full chat turn:
  1. Load/create conversation
  2. Run retrieval pipeline (exact -> fuzzy -> hybrid)
  3. Call the local LLM with grounded context (or a clarification/not-found prompt)
  4. Persist user + bot messages to MongoDB
  5. Return a structured ChatResponse
"""
import logging
import re
import uuid
from typing import Optional, List, Dict
from app.config import settings
from app.database.mongodb import conversations_col, messages_col, now
from app.rag.retriever import retrieve
from app.services import llm
from app.services.language import normalize_language_name
from app.utils.chitchat_handler import detect_chitchat, get_chitchat_response
from app.i18n.messages import get_message
from app.services.translator import translate_text

logger = logging.getLogger("doj_rag.chat_service")


def _get_or_create_conversation(conversation_id: Optional[str], user_id: str, first_message: str) -> str:
    if conversation_id:
        existing = conversations_col().find_one({"conversation_id": conversation_id})
        # Only reuse the conversation if it exists AND belongs to this user -
        # otherwise fall through and mint a brand new ID, rather than letting
        # one account's messages be appended into (or collide with) another
        # account's conversation.
        if existing and existing.get("user_id") == user_id:
            return conversation_id
        conversation_id = None

    new_id = str(uuid.uuid4())
    title = (first_message[:60] + "...") if len(first_message) > 60 else first_message
    conversations_col().insert_one({
        "conversation_id": new_id,
        "user_id": user_id,
        "title": title,
        "created_at": now(),
        "updated_at": now(),
    })
    return new_id


def _recent_history(conversation_id: str, limit: int) -> List[Dict]:
    cursor = (
        messages_col()
        .find({"conversation_id": conversation_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    msgs = list(cursor)
    msgs.reverse()
    return msgs


def _save_message(conversation_id: str, sender: str, message: str, language: str,
                   sources: List[Dict]):
    messages_col().insert_one({
        "conversation_id": conversation_id,
        "sender": sender,
        "message": message,
        "language": language,
        "sources": sources,
        "created_at": now(),
    })
    conversations_col().update_one(
        {"conversation_id": conversation_id}, {"$set": {"updated_at": now()}}
    )


def _clean_legal_text(text: str) -> str:
    """Light cosmetic cleanup of amendment-marker artifacts (e.g. leading
    '[' from bracketed amendment insertions, stray footnote digits) so the
    fast-path direct answer reads cleanly without needing an LLM pass."""
    text = re.sub(r"^\s*[\[\(]\s*", "", text)      # leading bracket from amendment markers
    text = re.sub(r"\s*[\]\)]\s*$", "", text)      # trailing bracket
    text = re.sub(r"(?<=\w)\d{1,2}(?=[\[\(])", "", text)  # stray footnote digits before a bracket
    return text.strip()


def _format_direct_answer(chunks: List[Dict]) -> str:
    """
    Fast path: format an exact-match Article/Section/Rule chunk directly,
    with NO LLM call. This is what makes "What is Article 21?" near-instant
    instead of waiting 1-3 minutes for local LLM generation - for an exact
    verified legal reference, the retrieved text already IS the accurate,
    complete answer, so paraphrasing it through an LLM only adds latency
    without adding correctness. (General/hybrid questions still use the LLM,
    since there's no single authoritative passage to just return.)
    """
    first = chunks[0]
    label_bits = []
    if first.get("article"):
        label_bits.append(f"Article {first['article']}")
    elif first.get("section"):
        label_bits.append(f"Section {first['section']}")
    elif first.get("rule"):
        label_bits.append(f"Rule {first['rule']}")
    if first.get("title"):
        label_bits.append(first["title"])
    heading = " — ".join(label_bits) if label_bits else (first.get("document_name") or "")

    body = " ".join(_clean_legal_text(c["text"]) for c in chunks)
    return f"{heading}\n\n{body}" if heading else body


def _chunks_to_sources(chunks: List[Dict]) -> List[Dict]:
    sources = []
    seen = set()
    for c in chunks:
        key = (c.get("document_id"), c.get("article"), c.get("section"), c.get("rule"))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "document": c.get("document_name"),
            "document_type": c.get("document_type"),
            "part": c.get("part"),
            "chapter": c.get("chapter"),
            "article": c.get("article"),
            "section": c.get("section"),
            "rule": c.get("rule"),
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
        })
    return sources


def handle_chat_message(message: str, conversation_id: Optional[str], language: str,
                         user_id: str) -> Dict:
    if not message or not message.strip():
        raise ValueError("Message cannot be empty.")

    language = normalize_language_name(language)
    conversation_id = _get_or_create_conversation(conversation_id, user_id, message)

    _save_message(conversation_id, "user", message, language, [])

    # --- Fast path 0: chit-chat / meta questions ---------------------------
    # Answered instantly with no retrieval and no LLM call. This is what was
    # missing before: "Hindi aati hai?" (do you know Hindi?) was previously
    # falling through to legal retrieval and getting a rambling, off-topic
    # LLM answer generated from a weak keyword match.
    chitchat_category = detect_chitchat(message)
    if chitchat_category:
        answer = get_chitchat_response(chitchat_category, language)
        _save_message(conversation_id, "bot", answer, language, [])
        return {
            "conversation_id": conversation_id,
            "message": answer,
            "language": language,
            "sources": [],
            "needs_clarification": False,
            "suggestions": [],
        }

    history = _recent_history(conversation_id, settings.MAX_HISTORY_MESSAGES)

    result = retrieve(message)
    mode = result["mode"]

    if mode == "clarify":
        intent = result["intent"]
        ref_label = f"{intent['query_type'].capitalize()} {intent['number']}"
        suggestions = [f"{intent['query_type'].capitalize()} {s}" for s in result["suggestions"]]
        # Template answer in the user's language, no LLM call - this is a
        # fixed, short message and an LLM round-trip would only add latency.
        answer = get_message("clarify_template", language, ref=ref_label, suggestions=" / ".join(suggestions))
        _save_message(conversation_id, "bot", answer, language, [])
        return {
            "conversation_id": conversation_id,
            "message": answer,
            "language": language,
            "sources": [],
            "needs_clarification": True,
            "suggestions": result["suggestions"],
        }

    if mode == "not_found":
        intent = result["intent"]
        ref_label = f"{intent['query_type'].capitalize()} {intent['number']}"
        answer = get_message("not_found_template", language, ref=ref_label)
        _save_message(conversation_id, "bot", answer, language, [])
        return {
            "conversation_id": conversation_id,
            "message": answer,
            "language": language,
            "sources": [],
            "needs_clarification": False,
            "suggestions": [],
        }

    chunks = result["chunks"]

    if not chunks:
        answer = get_message("no_context_template", language)
        _save_message(conversation_id, "bot", answer, language, [])
        return {
            "conversation_id": conversation_id,
            "message": answer,
            "language": language,
            "sources": [],
            "needs_clarification": False,
            "suggestions": [],
        }

    sources = _chunks_to_sources(chunks)

    if mode in ("exact", "suggested"):
        # --- Fast path: exact/near-exact Article/Section/Rule match ---------
        # No general-purpose LLM generation call. The retrieved text IS the
        # verified legal answer, so this returns near-instantly instead of
        # waiting 1-3 minutes for local LLM generation on typical laptop
        # hardware. If a non-English language is selected, the composed
        # answer is translated (translate_text is a no-op for English, and
        # caches every other language's translation in MongoDB so the same
        # Article is never re-translated on a later request).
        answer = _format_direct_answer(chunks)
        answer = translate_text(answer, language)
        if mode == "suggested":
            note = get_message("suggested_prefix_template", language, number=result.get("suggested_number", ""))
            answer = note + answer
        _save_message(conversation_id, "bot", answer, language, sources)
        return {
            "conversation_id": conversation_id,
            "message": answer,
            "language": language,
            "sources": sources,
            "needs_clarification": False,
            "suggestions": [],
        }

    # --- Hybrid/general question: still needs the LLM to synthesize an -----
    # answer across multiple chunks, but with speed-oriented settings (short
    # history, capped output length, streaming under the hood) - see llm.py.
    try:
        answer = llm.generate_answer(message, chunks, language, history)
    except llm.OllamaUnavailableError as e:
        logger.error(str(e))
        # Graceful degrade: return the raw retrieved legal text if the LLM is down,
        # rather than failing the whole request.
        top = chunks[0]
        answer = (
            f"(Local LLM unavailable, showing retrieved legal text directly)\n\n"
            f"{top['text']}"
        )

    _save_message(conversation_id, "bot", answer, language, sources)

    return {
        "conversation_id": conversation_id,
        "message": answer,
        "language": language,
        "sources": sources,
        "needs_clarification": False,
        "suggestions": [],
    }
