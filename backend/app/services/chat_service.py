"""
Orchestrates a full chat turn:
  1. Load/create conversation
  2. Run retrieval pipeline (exact -> fuzzy -> hybrid)
  3. Call the local LLM with grounded context (or a clarification/not-found prompt)
  4. Persist user + bot messages to MongoDB
  5. Yield the answer as a stream of events (see stream_chat_message)

Streamed as events rather than returned as one blocking call, so the caller
(the /api/chat route) can forward tokens to the browser as they're
generated - the user sees the answer build up in real time instead of
waiting in silence for however long full generation takes, and the request
becomes cancellable (aborting the connection stops generation server-side
too, instead of wasting compute on an answer nobody will see).
"""
import logging
import re
import uuid
from typing import Optional, List, Dict, AsyncGenerator
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


async def stream_chat_message(message: str, conversation_id: Optional[str], language: str,
                               user_id: str) -> AsyncGenerator[Dict, None]:
    """
    Yields event dicts as the answer is produced:
      {"type": "chunk", "text": "..."}        - append this text to the answer
      {"type": "phase", "phase": "translating"} - UI hint, no text change
      {"type": "replace", "text": "..."}       - replace the answer built so
                                                  far with this (used when a
                                                  translation pass swaps out
                                                  a streamed English draft)
      {"type": "done", "conversation_id", "sources", "language",
                "needs_clarification", "suggestions"}
      {"type": "error", "message": "..."}
    The final saved message in MongoDB always matches what "done" implies -
    whatever was last shown via chunk/replace events.
    """
    if not message or not message.strip():
        raise ValueError("Message cannot be empty.")

    language = normalize_language_name(language)
    conversation_id = _get_or_create_conversation(conversation_id, user_id, message)

    _save_message(conversation_id, "user", message, language, [])

    # --- Fast path 0: chit-chat / meta questions ---------------------------
    chitchat_category = detect_chitchat(message)
    if chitchat_category:
        answer = get_chitchat_response(chitchat_category, language)
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language)
        return

    history = _recent_history(conversation_id, settings.MAX_HISTORY_MESSAGES)

    result = retrieve(message)
    mode = result["mode"]

    if mode == "clarify":
        intent = result["intent"]
        ref_label = f"{intent['query_type'].capitalize()} {intent['number']}"
        suggestions = [f"{intent['query_type'].capitalize()} {s}" for s in result["suggestions"]]
        answer = get_message("clarify_template", language, ref=ref_label, suggestions=" / ".join(suggestions))
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language, needs_clarification=True, suggestions=result["suggestions"])
        return

    if mode == "not_found":
        intent = result["intent"]
        ref_label = f"{intent['query_type'].capitalize()} {intent['number']}"
        answer = get_message("not_found_template", language, ref=ref_label)
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language)
        return

    chunks = result["chunks"]

    if not chunks:
        answer = get_message("no_context_template", language)
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language)
        return

    sources = _chunks_to_sources(chunks)

    if mode in ("exact", "suggested"):
        # --- Fast path: exact/near-exact Article/Section/Rule match ---------
        # Already near-instant (no open-ended generation) - translation (if
        # needed) is a single short, cached call, not worth streaming
        # token-by-token, so this is yielded as one chunk.
        answer = _format_direct_answer(chunks)
        if language != "English":
            yield {"type": "phase", "phase": "translating"}
        answer = translate_text(answer, language)
        if mode == "suggested":
            note = get_message("suggested_prefix_template", language, number=result.get("suggested_number", ""))
            answer = note + answer
        _save_message(conversation_id, "bot", answer, language, sources)
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language, sources=sources)
        return

    # --- Hybrid/general question: needs the LLM to synthesize an answer -----
    # across multiple chunks. Generation is streamed in English first (the
    # model is faster and more reliable composing English than Indic
    # scripts directly, and Indic scripts also need more output tokens per
    # sentence - both were contributing to the old multi-minute/timeout
    # behavior), so the user sees real progress within seconds instead of
    # silence. If a non-English language is selected, a second short call
    # (via the smaller, dedicated translation model) converts the finished
    # answer - shown as a brief "translating" phase rather than another long
    # silent wait.
    english_parts = []
    try:
        async for delta in llm.stream_answer(message, chunks, "English", history):
            english_parts.append(delta)
            yield {"type": "chunk", "text": delta}
        answer_en = "".join(english_parts).strip()

        if language != "English":
            yield {"type": "phase", "phase": "translating"}
            answer = translate_text(answer_en, language)
            yield {"type": "replace", "text": answer}
        else:
            answer = answer_en
    except llm.OllamaUnavailableError as e:
        logger.error(str(e))
        # Graceful degrade: return the raw retrieved legal text if the LLM is
        # slow/down, rather than failing the whole request with a 500 (this
        # is exactly the failure mode that used to happen on a timeout).
        top = chunks[0]
        answer = (
            f"(Local LLM unavailable or too slow right now, showing retrieved "
            f"legal text directly)\n\n{top['text']}"
        )
        answer = translate_text(answer, language)
        yield {"type": "replace", "text": answer}

    _save_message(conversation_id, "bot", answer, language, sources)
    yield _done_event(conversation_id, language, sources=sources)


def _done_event(conversation_id: str, language: str, sources: List[Dict] = None,
                 needs_clarification: bool = False, suggestions: List[str] = None) -> Dict:
    return {
        "type": "done",
        "conversation_id": conversation_id,
        "language": language,
        "sources": sources or [],
        "needs_clarification": needs_clarification,
        "suggestions": suggestions or [],
    }
