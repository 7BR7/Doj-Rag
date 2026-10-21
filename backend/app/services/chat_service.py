"""
Orchestrates a full chat turn:
  1. Load/create conversation
    2. Answer casual/general questions directly, or retrieve legal context
    3. Call the LLM with legal context when needed (or a clarification/not-found prompt)
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
from app.database.mongodb import conversations_col, messages_col, documents_col, chunks_col, now
from app.rag.retriever import retrieve
from app.services import llm
from app.services.language import (
    normalize_language_name,
    detect_script_language,
    resolve_turn_language,
)
from app.utils.chitchat_handler import detect_chitchat, get_chitchat_response
from app.i18n.messages import get_message
from app.services.translator import (
    translate_text,
    stream_translate_text,
    TranslationUnavailableError,
)
from app.utils.legal_query_parser import is_legal_query
from app.rag.query_router import classify_query, QUERY_TYPE_GENERAL, QUERY_TYPE_LEGAL, QUERY_TYPE_PDF_SPECIFIC, QUERY_TYPE_HYBRID

logger = logging.getLogger("doj_rag.chat_service")


def _get_or_create_conversation(conversation_id: Optional[str], user_id: str, first_message: str) -> str:
    title = (first_message[:60] + "...") if len(first_message) > 60 else first_message
    if conversation_id:
        existing = conversations_col().find_one({"conversation_id": conversation_id})
        # Only reuse the conversation if it exists AND belongs to this user -
        # otherwise fall through and mint a brand new ID, rather than letting
        # one account's messages be appended into (or collide with) another
        # account's conversation.
        if existing and existing.get("user_id") == user_id:
            if existing.get("title") == "New conversation":
                conversations_col().update_one(
                    {"conversation_id": conversation_id, "user_id": user_id},
                    {"$set": {"title": title}},
                )
            return conversation_id
        conversation_id = None

    new_id = str(uuid.uuid4())
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
    unique_chunks = []
    seen_chunks = set()
    for chunk in chunks:
        key = (
            chunk.get("document_id"),
            chunk.get("article"),
            chunk.get("section"),
            chunk.get("rule"),
            chunk.get("child_index"),
            chunk.get("text"),
        )
        if key not in seen_chunks:
            seen_chunks.add(key)
            unique_chunks.append(chunk)

    if not unique_chunks:
        return ""

    first = unique_chunks[0]
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

    body = " ".join(_clean_legal_text(c["text"]) for c in unique_chunks)
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
                               user_id: str, override_language: bool = False,
                               document_id: Optional[str] = None) -> AsyncGenerator[Dict, None]:
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

    # Determine the authoritative response language for THIS specific user message.
    # The language of the current message always takes precedence over stale dropdowns.
    # Explicit manual override is respected if user intentionally chose a language.
    language = resolve_turn_language(
        message=message,
        requested_language=language,
        override_language=override_language,
    )

    conversation_id = _get_or_create_conversation(conversation_id, user_id, message)

    # Important: Fetch history BEFORE inserting the current user message into MongoDB.
    # This prevents the current message from being duplicated in LLM conversation context.
    history = _recent_history(conversation_id, settings.MAX_HISTORY_MESSAGES)

    _save_message(conversation_id, "user", message, language, [])

    # --- Fast path 0: chit-chat / meta questions ---------------------------
    chitchat_category = detect_chitchat(message)
    if chitchat_category:
        answer = get_chitchat_response(chitchat_category, language)
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language)
        return

    if document_id:
        document = documents_col().find_one({"document_id": document_id})
        if not document:
            answer = get_message("no_context_template", language)
            _save_message(conversation_id, "bot", answer, language, [])
            yield {"type": "chunk", "text": answer}
            yield _done_event(conversation_id, language)
            return

        document_chunks = list(
            chunks_col()
            .find({"document_id": document_id, "source_type": "actual_law", "child_index": 0})
            .sort("page_start", 1)
        )
        if not document_chunks:
            document_chunks = list(
                chunks_col().find({"document_id": document_id}).sort("page_start", 1).limit(10)
            )
        if len(document_chunks) > 8:
            last_index = len(document_chunks) - 1
            sample_indices = {round(i * last_index / 7) for i in range(8)}
            document_chunks = [chunk for i, chunk in enumerate(document_chunks) if i in sample_indices]
        for chunk in document_chunks:
            chunk["text"] = chunk.get("text", "")[:600]

        if not document_chunks:
            answer = get_message("no_context_template", language)
            _save_message(conversation_id, "bot", answer, language, [])
            yield {"type": "chunk", "text": answer}
            yield _done_event(conversation_id, language)
            return

        summary_request = (
            f"Summarize the selected document '{document.get('document_name', document_id)}' "
            "for a non-lawyer. Explain its purpose and the main topics or procedures. "
            "Use only the supplied excerpts; say briefly if the excerpts do not cover the full document."
        )
        summary_parts = []
        try:
            async for delta in llm.stream_answer(summary_request, document_chunks, language, []):
                summary_parts.append(delta)
                yield {"type": "chunk", "text": delta}
        except (llm.OllamaUnavailableError, llm.LLMUnavailableError) as e:
            logger.error("Document summary unavailable: %s", e)
            answer = get_message("llm_unavailable", language)
            _save_message(conversation_id, "bot", answer, language, [])
            yield {"type": "replace", "text": answer}
            yield _done_event(conversation_id, language)
            return

        answer = "".join(summary_parts).strip()
        sources = _chunks_to_sources(document_chunks)
        _save_message(conversation_id, "bot", answer, language, sources)
        yield _done_event(conversation_id, language, sources=sources)
        return

    # --- Intelligent Query Classification & Routing ----------------------
    classification = classify_query(message, document_id=document_id)
    route = classification["route"]
    logger.info("Intelligent Query Route: %s (confidence: %.2f, reason: %s)",
                route, classification.get("confidence", 0.0), classification.get("reason", ""))

    # If general non-legal query, stream directly without forcing PDF retrieval
    if route == QUERY_TYPE_GENERAL:
        parts = []
        try:
            async for delta in llm.stream_general_answer(message, language, history):
                parts.append(delta)
                yield {"type": "chunk", "text": delta}
        except llm.LLMUnavailableError as e:
            logger.error("General answer unavailable: %s", e)
            answer = get_message("llm_unavailable", language)
            _save_message(conversation_id, "bot", answer, language, [])
            yield {"type": "replace", "text": answer}
            yield _done_event(conversation_id, language)
            return
        answer = "".join(parts).strip()
        _save_message(conversation_id, "bot", answer, language, [])
        yield _done_event(conversation_id, language)
        return

    result = retrieve(message)
    mode = result["mode"]

    # Extract NLP intent & query classification
    detected_intent = None
    query_confidence = 1.0
    related_provisions = []
    try:
        from app.nlp.ml_intent import classify_intent
        intent_res = classify_intent(message)
        detected_intent = intent_res.get("intent")
        query_confidence = intent_res.get("confidence", 1.0)
    except Exception:
        try:
            from app.nlp.nlp_pipeline import detect_intent
            detected_intent = detect_intent(message)
        except Exception:
            pass

    try:
        from app.nlp.knowledge_graph import get_related_provisions
        intent_info = result.get("intent", {})
        q_type = intent_info.get("query_type")
        q_num = intent_info.get("number")
        if q_type in ("article", "section") and q_num:
            related_provisions = get_related_provisions(q_type.capitalize(), q_num, max_hops=1, max_results=4)
    except Exception:
        pass

    if mode == "clarify":
        intent = result["intent"]
        ref_label = f"{intent['query_type'].capitalize()} {intent['number']}"
        suggestions = [f"{intent['query_type'].capitalize()} {s}" for s in result["suggestions"]]
        answer = get_message("clarify_template", language, ref=ref_label, suggestions=" / ".join(suggestions))
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(
            conversation_id,
            language,
            needs_clarification=True,
            suggestions=result["suggestions"],
            intent=detected_intent,
        )
        return

    if mode == "clarify_act":
        intent = result["intent"]
        answer = get_message(
            "ambiguous_act_template",
            language,
            number=intent["number"],
            acts=", ".join(result["act_names"]),
        )
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(
            conversation_id, language, needs_clarification=True,
            suggestions=result["act_names"],
        )
        return

    if mode == "not_found":
        intent = result["intent"]
        ref_label = f"{intent['query_type'].capitalize()} {intent['number']}"
        answer = get_message("not_found_template", language, ref=ref_label)
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language, intent=detected_intent)
        return

    chunks = result["chunks"]

    if mode in ("exact", "suggested"):
        intent = result.get("intent", {})
        number_field = {
            "article": "article",
            "section": "section",
            "rule": "rule",
        }.get(intent.get("query_type"))
        if number_field:
            primary_chunks = [
                chunk for chunk in chunks
                if str(chunk.get(number_field)) == str(intent.get("number"))
            ]
            if primary_chunks:
                chunks = primary_chunks

    if not chunks:
        answer = get_message("no_context_template", language)
        _save_message(conversation_id, "bot", answer, language, [])
        yield {"type": "chunk", "text": answer}
        yield _done_event(conversation_id, language, intent=detected_intent)
        return

    sources = _chunks_to_sources(chunks)

    if mode in ("exact", "suggested"):
        # Keep exact legal context, but answer in a short conversational form.
        source_answer = _format_direct_answer(chunks)
        prefix = ""
        if mode == "suggested":
            prefix = get_message(
                "suggested_prefix_template",
                language,
                number=result.get("suggested_number", ""),
            )
            yield {"type": "chunk", "text": prefix}

        answer_parts = []
        try:
            async for delta in llm.stream_answer(message, chunks, language, history):
                answer_parts.append(delta)
                yield {"type": "chunk", "text": delta}
            answer = "".join(answer_parts).strip()
            if not answer:
                answer = source_answer
                if language != "English":
                    answer = translate_text(answer, language)
                yield {"type": "replace", "text": answer}
            else:
                from app.rag.response_validator import validate_response, clean_repetitions_and_normalize
                answer = clean_repetitions_and_normalize(answer)
                v_res = validate_response(answer, language, chunks)
                if not v_res["is_valid"]:
                    logger.info("Exact answer quality issue (%s). Repairing or fallback translating...", v_res["reason"])
                    yield {"type": "phase", "phase": "translating"}
                    if language != "English":
                        translated = translate_text(source_answer, language)
                        if translated and len(translated) > 20:
                            answer = translated
                            yield {"type": "replace", "text": answer}
                    else:
                        answer = source_answer
                        yield {"type": "replace", "text": answer}
        except (llm.OllamaUnavailableError, llm.LLMUnavailableError):
            logger.warning("Concise legal answer generation unavailable; returning the provision text.")
            answer = source_answer
            if language != "English":
                translated_parts = []
                try:
                    async for delta in stream_translate_text(source_answer, language):
                        translated_parts.append(delta)
                        yield {"type": "chunk", "text": delta}
                    answer = "".join(translated_parts).strip()
                except TranslationUnavailableError:
                    answer = get_message("translation_unavailable", language)
            yield {"type": "replace", "text": answer}
        answer = prefix + answer
        if prefix and answer_parts:
            yield {"type": "replace", "text": answer}
        _save_message(conversation_id, "bot", answer, language, sources)
            
        # Verify citations and legal fact-checking
        citation_info = {}
        why_answer = ""
        try:
            from app.rag.citation_verifier import verify_answer_citations
            from app.rag.fact_checker import fact_check_legal_claims
            
            # Run deterministic legal fact-checking
            fact_check = fact_check_legal_claims(answer, chunks)
            if not fact_check["is_factually_accurate"] and fact_check["corrections"]:
                logger.warning("Factual correction triggered: %s", fact_check["factual_errors"])
                answer = fact_check["corrected_text"]
                yield {"type": "replace", "text": answer}

            citation_info = verify_answer_citations(answer, chunks)
            citation_info["fact_check"] = {
                "is_factually_accurate": fact_check["is_factually_accurate"],
                "factual_errors": fact_check["factual_errors"],
                "verified_articles": fact_check["verified_articles"]
            }
            why_answer = citation_info.get("why_this_answer", "")
        except Exception as e:
            logger.debug("Fact-check/citation verification pass skipped: %s", e)

        yield _done_event(
            conversation_id,
            language,
            sources=sources,
            intent=detected_intent,
            related_provisions=related_provisions,
            citation_verification=citation_info,
            why_this_answer=why_answer
        )
        return

    # --- Hybrid/general question: needs the LLM to synthesize an answer -----
    # across multiple chunks.
    #
    # SINGLE-PASS (default, settings.HYBRID_SINGLE_PASS=True): stream the
    # answer directly in the target language in ONE LLM call, backed by the
    # explicit language reminder in llm.py. This is the faster of the two
    # strategies - for non-English questions it's roughly HALF the LLM time
    # of the alternative below, since there's no separate translation call.
    #
    # TWO-PASS (settings.HYBRID_SINGLE_PASS=False): generate in English
    # first, then translate with the smaller dedicated model. Slower (two
    # sequential calls) but can be more reliable for languages/models where
    # direct non-English generation is noticeably weaker - kept as an
    # opt-in fallback via .env, not the default, since speed is the
    # priority here.
    # Determine prompt type according to intelligent query classification
    prompt_type = "base"
    if route == QUERY_TYPE_PDF_SPECIFIC:
        prompt_type = "document"
    elif route == QUERY_TYPE_HYBRID:
        prompt_type = "hybrid"

    if settings.HYBRID_SINGLE_PASS:
        parts = []
        try:
            async for delta in llm.stream_answer(message, chunks, language, history, prompt_type=prompt_type):
                parts.append(delta)
                yield {"type": "chunk", "text": delta}
            answer = "".join(parts).strip()
            from app.rag.response_validator import validate_response, clean_repetitions_and_normalize
            answer = clean_repetitions_and_normalize(answer)
            
            # Run quality validation
            v_res = validate_response(answer, language, chunks)
            if not v_res["is_valid"]:
                logger.info("Single-pass output failed validation (%s). Triggering fallback translation...", v_res["reason"])
                yield {"type": "phase", "phase": "translating"}
                # Generate clean English grounding draft if needed, then translate
                english_draft = answer
                from app.services.translator import _has_target_script
                if (_has_target_script(answer, language) and v_res["code"] == "EXCESSIVE_REPETITION") or v_res["code"] == "ABRUPT_TRUNCATION":
                    # Re-summarize chunks directly
                    english_draft = " ".join(c.get("text", "") for c in chunks[:2]) if chunks else ""
                translated_answer = translate_text(english_draft, language)
                if translated_answer and len(translated_answer) > 20:
                    answer = clean_repetitions_and_normalize(translated_answer)
                    yield {"type": "replace", "text": answer}
        except (llm.OllamaUnavailableError, llm.LLMUnavailableError) as e:
            logger.error(str(e))
            top = chunks[0]
            answer = (
                f"(Local LLM unavailable or too slow right now, showing retrieved "
                f"legal text directly)\n\n{top['text']}"
            )
            answer = translate_text(answer, language)
            yield {"type": "replace", "text": answer}

        # Verify citations and legal fact-checking
        citation_info = {}
        why_answer = ""
        try:
            from app.rag.citation_verifier import verify_answer_citations
            from app.rag.fact_checker import fact_check_legal_claims
            
            # Run deterministic legal fact-checking
            fact_check = fact_check_legal_claims(answer, chunks)
            if not fact_check["is_factually_accurate"] and fact_check["corrections"]:
                logger.warning("Factual correction triggered: %s", fact_check["factual_errors"])
                answer = fact_check["corrected_text"]
                yield {"type": "replace", "text": answer}

            citation_info = verify_answer_citations(answer, chunks)
            citation_info["fact_check"] = {
                "is_factually_accurate": fact_check["is_factually_accurate"],
                "factual_errors": fact_check["factual_errors"],
                "verified_articles": fact_check["verified_articles"]
            }
            why_answer = citation_info.get("why_this_answer", "")
        except Exception as e:
            logger.debug("Fact-check/citation verification pass skipped: %s", e)

        _save_message(conversation_id, "bot", answer, language, sources)
        yield _done_event(
            conversation_id,
            language,
            sources=sources,
            intent=detected_intent,
            related_provisions=related_provisions,
            citation_verification=citation_info,
            why_this_answer=why_answer
        )
        return

    # --- Two-pass fallback path ---------------------------------------------
    english_parts = []
    try:
        async for delta in llm.stream_answer(message, chunks, "English", history, prompt_type=prompt_type):
            english_parts.append(delta)
            yield {"type": "chunk", "text": delta}
        answer_en = "".join(english_parts).strip()

        if language != "English":
            yield {"type": "phase", "phase": "translating"}
            answer = translate_text(answer_en, language)
            yield {"type": "replace", "text": answer}
        else:
            answer = answer_en
    except (llm.OllamaUnavailableError, llm.LLMUnavailableError) as e:
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
    yield _done_event(
        conversation_id,
        language,
        sources=sources,
        intent=detected_intent,
        related_provisions=related_provisions,
    )


def _done_event(conversation_id: str, language: str, sources: List[Dict] = None,
                 needs_clarification: bool = False, suggestions: List[str] = None,
                 intent: Optional[str] = None, related_provisions: List[Dict] = None,
                 citation_verification: Optional[Dict] = None, why_this_answer: Optional[str] = None) -> Dict:
    return {
        "type": "done",
        "conversation_id": conversation_id,
        "language": language,
        "sources": sources or [],
        "needs_clarification": needs_clarification,
        "suggestions": suggestions or [],
        "intent": intent,
        "related_provisions": related_provisions or [],
        "citation_verification": citation_verification or {},
        "why_this_answer": why_this_answer or ""
    }
