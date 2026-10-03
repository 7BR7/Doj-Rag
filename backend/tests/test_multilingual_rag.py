"""
Automated unit & integration tests for DOJ-RAG Multilingual & Language Dynamics:
  - Indic numeral normalization
  - Multilingual legal query parsing (Telugu, Hindi, Tamil, Kannada, English)
  - Dynamic language resolution (auto-detect, stale dropdown prevention, manual override)
  - End-to-end exact match retrieval with non-English queries
  - Voice transcription route with language parameter
"""
from app.utils.legal_query_parser import is_legal_query, parse_legal_query, normalize_indic_digits
from app.services.language import (
    detect_script_language,
    detect_language_from_text,
    resolve_turn_language,
    normalize_language_name,
)
from app.rag.retriever import retrieve
from app.rag.document_loader import detect_document_type
from app.rag.parser_router import route_and_parse
from app.rag.constitution_parser import parse_constitution
from app.utils.chitchat_handler import detect_chitchat, get_chitchat_response
from app.i18n.messages import get_message


def test_indic_digit_normalization():
    # Telugu digits
    assert normalize_indic_digits("౨౧") == "21"
    assert normalize_indic_digits("అధికరణ ౨౧A") == "అధికరణ 21A"

    # Devanagari digits
    assert normalize_indic_digits("२१") == "21"
    assert normalize_indic_digits("अनुच्छेद २१") == "अनुच्छेद 21"

    # Bengali digits
    assert normalize_indic_digits("২১") == "21"

    # Tamil digits
    assert normalize_indic_digits("௨௧") == "21"

    # Mixed ASCII & text
    assert normalize_indic_digits("Article 21") == "Article 21"


def test_multilingual_article_parsing():
    # Telugu
    q1 = parse_legal_query("ఆర్టికల్ 21 ఏమిటి?")
    assert q1["query_type"] == "article"
    assert q1["number"] == "21"

    q2 = parse_legal_query("అధికరణ 21A గురించి చెప్పండి")
    assert q2["query_type"] == "article"
    assert q2["number"] == "21A"

    q3 = parse_legal_query("21వ అధికరణం ఏమిటి?")
    assert q3["query_type"] == "article"
    assert q3["number"] == "21"

    # Hindi
    q4 = parse_legal_query("अनुच्छेद 21 क्या है?")
    assert q4["query_type"] == "article"
    assert q4["number"] == "21"

    q5 = parse_legal_query("अनुच्छेद २१A के बारे में बताएं")
    assert q5["query_type"] == "article"
    assert q5["number"] == "21A"

    # Tamil
    q6 = parse_legal_query("சரத்து 21 என்ன?")
    assert q6["query_type"] == "article"
    assert q6["number"] == "21"

    tamil_ordinal = parse_legal_query("19வது சரத்து என்ன?")
    assert tamil_ordinal["query_type"] == "article"
    assert tamil_ordinal["number"] == "19"
    assert tamil_ordinal["document_hint"] == "constitution"

    tamil_ordinal_formal = parse_legal_query("19ஆம் சரத்து பற்றி சொல்லுங்கள்")
    assert tamil_ordinal_formal["query_type"] == "article"
    assert tamil_ordinal_formal["number"] == "19"

    tamil_short_form = parse_legal_query("சட்டம் 19")
    assert tamil_short_form["query_type"] == "article"
    assert tamil_short_form["number"] == "19"
    assert tamil_short_form["document_hint"] == "constitution"

    ordinal_article_queries = [
        "19వ అధికరణం",
        "19वां अनुच्छेद",
        "19வது சரத்து",
        "19ನೇ ವಿಧಿ",
        "19ാം അനുച്ഛേദം",
        "19তম অনুচ্ছেদ",
        "19वा अनुच्छेद",
        "19મો અનુચ્છેદ",
        "19ਵਾਂ ਅਨੁਛੇਦ",
        "19ତମ ଅନୁଚ୍ଛେଦ",
        "19واں آرٹیکل",
    ]
    for ordinal_query in ordinal_article_queries:
        ordinal_intent = parse_legal_query(ordinal_query)
        assert ordinal_intent["query_type"] == "article", (ordinal_query, ordinal_intent)
        assert ordinal_intent["number"] == "19", (ordinal_query, ordinal_intent)

    # Kannada
    q7 = parse_legal_query("ವಿಧಿ 21 ಎಂದರೇನು?")
    assert q7["query_type"] == "article"
    assert q7["number"] == "21"

    # English
    q8 = parse_legal_query("What is Article 21?")
    assert q8["query_type"] == "article"
    assert q8["number"] == "21"


def test_multilingual_section_and_rule_parsing():
    # Telugu Section
    s1 = parse_legal_query("సెక్షన్ 302 ప్రకారం ఏమిటి?")
    assert s1["query_type"] == "section"
    assert s1["number"] == "302"

    # Hindi Section
    s2 = parse_legal_query("धारा 302 क्या है?")
    assert s2["query_type"] == "section"
    assert s2["number"] == "302"

    # Rule
    r1 = parse_legal_query("రూల్ 5 వివరించండి")
    assert r1["query_type"] == "rule"
    assert r1["number"] == "5"

    r2 = parse_legal_query("नियम 10 क्या है?")
    assert r2["query_type"] == "rule"
    assert r2["number"] == "10"

    # Tamil ordinal section numbers, including common mixed-script speech transcription
    s3 = parse_legal_query("47வது பிரிவு என்ன?")
    assert s3["query_type"] == "section"
    assert s3["number"] == "47"

    spoken_tamil = "இந்திய சட்டத்தின் 40 செவனாவது பிரிவை எனக்கு வேண்டும்"
    s4 = parse_legal_query(spoken_tamil)
    assert s4["query_type"] == "section"
    assert s4["number"] == "47"
    assert is_legal_query(spoken_tamil)


def test_bharatiya_statutes_route_and_extract_plain_section_headings():
    pages = [
        "THE BHARATIYA NYAYA SANHITA, 2023\n"
        "47. A person abets an offence beyond India which would be an offence in India."
    ]
    assert detect_document_type(pages, "bns.pdf") == "act"
    document = {
        "filename": "bns.pdf",
        "document_id": "bns",
        "document_type": "act",
        "pages": pages,
        "toc_pages": set(),
    }
    units = route_and_parse(document)
    assert any(unit["unit_type"] == "section" and unit["number"] == "47" for unit in units)

    manual_pages = ["15. Click the save button to continue to the next screen."]
    manual = {
        "filename": "user_manual.pdf",
        "document_id": "user_manual",
        "document_type": "generic",
        "pages": manual_pages,
        "toc_pages": set(),
    }
    assert all(unit["unit_type"] != "section" for unit in route_and_parse(manual))


def test_constitution_parser_accepts_wrapped_article_titles():
    pages = [
        "PART IV\n"
        "9. Protection of interests of minorities.—The State shall protect them.\n"
        "13. Laws inconsistent with fundamental rights.—All laws are subject to this article.\n"
        "15. Prohibition of discrimination on grounds of religion, race, caste.—The State shall not discriminate.\n"
        "27. Freedom as to payment of taxes for promotion of any particular religion.—No person shall be compelled.\n"
        "47. Duty of the State to raise the level of nutrition and the standard\n"
        "of living and to improve public health.—The State shall regard the raising\n"
        "of the level of nutrition and the standard of living as primary duties.\n"
        "48. Organisation of agriculture and animal husbandry.—The State shall organise."
    ]
    articles = parse_constitution("constitution", "Constitution", pages, set())
    assert {article["number"] for article in articles} >= {"9", "13", "15", "27", "47"}
    article_47 = next(article for article in articles if article["number"] == "47")
    assert "improve public health" in article_47["title"]
    assert "The State shall regard" in article_47["body"]


def test_constitution_parser_ignores_toc_and_keeps_article_bodies_separate():
    pages = [
        "CONTENTS\nARTICLES\n"
        "1. Name and territory of the Union.\n"
        "2. Admission or establishment of new States.\n"
        "3. Formation of new States.\n"
        "PART I\nTHE UNION AND ITS TERRITORY\n"
        "1. Name and territory of the Union.—India, that is Bharat, shall be a Union of States.\n"
        "(2) The States and the territories thereof shall be as specified in the First Schedule.\n"
        "2. Admission or establishment of new States.—Parliament may by law admit into the Union.\n"
        "3. Formation of new States.—Parliament may by law form a new State."
    ]
    articles = parse_constitution("constitution", "Constitution", pages, set())
    article_1 = next(article for article in articles if article["number"] == "1")
    article_2 = next(article for article in articles if article["number"] == "2")
    assert article_1["title"] == "Name and territory of the Union"
    assert "India, that is Bharat" in article_1["body"]
    assert "Admission or establishment of new States" not in article_1["title"]
    assert "Parliament may by law admit" not in article_1["body"]
    assert "Parliament may by law admit" in article_2["body"]


def test_legal_query_routing():
    assert is_legal_query("What is Article 21?")
    assert is_legal_query("What rights does a tenant have?")
    assert is_legal_query("अनुच्छेद 21 क्या है?")
    assert not is_legal_query("How do I make pancakes?")
    assert not is_legal_query("Can you explain photosynthesis?")


def test_script_and_language_detection():
    # Native scripts
    assert detect_script_language("ఆర్టికల్ 21 ఏమిటి?") == "Telugu"
    assert detect_script_language("अनुच्छेद 21 क्या है?") == "Hindi"
    assert detect_script_language("சரத்து 21 என்ன?") == "Tamil"
    assert detect_script_language("What is Article 21?") == "English"

    # Romanized / transliterated
    assert detect_language_from_text("Article 21 kya hai?") == "Hindi"
    assert detect_language_from_text("Article 21 gurinchi cheppandi") == "Telugu"
    assert detect_language_from_text("Article 21 enna?") == "Tamil"
    assert detect_language_from_text("What is Article 21?") == "English"


def test_language_resolution_dynamics():
    # 1. Native Telugu message with stale English dropdown -> Telugu wins
    assert resolve_turn_language("ఆర్టికల్ 21 ఏమిటి?", requested_language="English") == "Telugu"

    # 2. English message with stale Telugu dropdown -> English wins (stale dropdown ignored)
    assert resolve_turn_language("What is Article 21?", requested_language="Telugu") == "English"

    # 3. Native Hindi message with stale English dropdown -> Hindi wins
    assert resolve_turn_language("अनुच्छेद 21 क्या है?", requested_language="English") == "Hindi"

    # 4. Manual user override: English message with manual override to Telugu
    assert resolve_turn_language("What is Article 21?", requested_language="Telugu", override_language=True) == "Telugu"

    # 5. Manual override: English message with manual override to Hindi
    assert resolve_turn_language("Explain the right to education", requested_language="Hindi", override_language=True) == "Hindi"

    # 6. Romanized query with Auto-Detect
    assert resolve_turn_language("Article 21 kya hai?", requested_language="Auto-Detect") == "Hindi"


def test_hindi_help_question_uses_localized_chitchat():
    message = "क्या तुम मुझे हेल्प कर सकते हो"
    assert detect_chitchat(message) == "who_are_you"
    assert "कानूनी सहायक" in get_chitchat_response("who_are_you", "Hindi")


def test_tamil_greeting_with_name_uses_localized_chitchat():
    assert detect_chitchat("வணக்கம் ராக்தாஸ்.") == "greeting"
    assert get_chitchat_response("greeting", "Tamil").startswith("வணக்கம்")


def test_llm_unavailable_message_is_localized():
    assert "Ollama" in get_message("llm_unavailable", "Tamil")


def test_translation_fallback_stays_in_requested_language():
    from types import SimpleNamespace
    from app.database import mongodb
    from app.services import translator

    original_get_db = mongodb.get_db
    original_generate = translator.generate_raw
    mongodb.get_db = lambda: SimpleNamespace(
        translations=SimpleNamespace(
            find_one=lambda query: None,
            update_one=lambda *args, **kwargs: None,
        )
    )
    translator.generate_raw = lambda *args, **kwargs: "English source text"
    try:
        result = translator.translate_text("English source text", "Tamil")
    finally:
        mongodb.get_db = original_get_db
        translator.generate_raw = original_generate

    assert result == get_message("translation_unavailable", "Tamil")
    assert any("\u0b80" <= char <= "\u0bff" for char in result)


def test_general_chat_handles_unavailable_llm_in_tamil():
    import asyncio
    from app.services import chat_service, llm

    async def unavailable_stream(*args, **kwargs):
        raise llm.LLMUnavailableError("Ollama is unavailable")
        yield ""

    original_create = chat_service._get_or_create_conversation
    original_history = chat_service._recent_history
    original_save = chat_service._save_message
    original_stream = chat_service.llm.stream_general_answer
    chat_service._get_or_create_conversation = lambda *args: "test-conversation"
    chat_service._recent_history = lambda *args: []
    chat_service._save_message = lambda *args: None
    chat_service.llm.stream_general_answer = unavailable_stream

    async def collect_events():
        return [event async for event in chat_service.stream_chat_message(
            message="இன்று வானிலை எப்படி இருக்கும்?",
            conversation_id=None,
            language="Auto-Detect",
            user_id="test-user",
        )]

    try:
        events = asyncio.run(collect_events())
    finally:
        chat_service._get_or_create_conversation = original_create
        chat_service._recent_history = original_history
        chat_service._save_message = original_save
        chat_service.llm.stream_general_answer = original_stream

    replacement = next(event for event in events if event["type"] == "replace")
    assert "Ollama" in replacement["text"]
    assert events[-1]["type"] == "done"


def test_document_summary_uses_only_selected_document_chunks():
    import asyncio
    from app.services import chat_service

    class FakeCursor(list):
        def sort(self, *args, **kwargs):
            return self

    documents = {
        "bns": {"document_id": "bns", "document_name": "Bharatiya Nyaya Sanhita"},
        "bsa": {"document_id": "bsa", "document_name": "Bharatiya Sakshya Adhiniyam"},
    }
    chunks = [
        {"document_id": "bns", "document_name": "BNS", "text": "BNS sample content", "source_type": "actual_law", "child_index": 0, "section": "1", "chunk_id": "bns-1"},
        {"document_id": "bsa", "document_name": "BSA", "text": "BSA unrelated content", "source_type": "actual_law", "child_index": 0, "section": "1", "chunk_id": "bsa-1"},
    ]

    class FakeDocuments:
        def find_one(self, query):
            return documents.get(query["document_id"])

    class FakeChunks:
        def find(self, query):
            return FakeCursor([chunk for chunk in chunks if chunk["document_id"] == query["document_id"]])

    observed = {}

    async def fake_answer(message, selected_chunks, language, history):
        observed["message"] = message
        observed["chunks"] = selected_chunks
        observed["language"] = language
        yield "இந்த ஆவணம் குற்றங்களையும் அவற்றுக்கான தண்டனைகளையும் விளக்குகிறது."

    originals = {
        "create": chat_service._get_or_create_conversation,
        "history": chat_service._recent_history,
        "save": chat_service._save_message,
        "documents": chat_service.documents_col,
        "chunks": chat_service.chunks_col,
        "answer": chat_service.llm.stream_answer,
    }
    saved = []
    chat_service._get_or_create_conversation = lambda *args: "summary-conversation"
    chat_service._recent_history = lambda *args: []
    chat_service._save_message = lambda *args: saved.append(args)
    chat_service.documents_col = lambda: FakeDocuments()
    chat_service.chunks_col = lambda: FakeChunks()
    chat_service.llm.stream_answer = fake_answer

    async def collect_events():
        return [event async for event in chat_service.stream_chat_message(
            message="இந்த ஆவணத்தை சுருக்கமாக கூறு",
            conversation_id="summary-conversation",
            language="Auto-Detect",
            user_id="test-user",
            document_id="bns",
        )]

    try:
        events = asyncio.run(collect_events())
    finally:
        chat_service._get_or_create_conversation = originals["create"]
        chat_service._recent_history = originals["history"]
        chat_service._save_message = originals["save"]
        chat_service.documents_col = originals["documents"]
        chat_service.chunks_col = originals["chunks"]
        chat_service.llm.stream_answer = originals["answer"]

    assert observed["language"] == "Tamil"
    assert len(observed["chunks"]) == 1
    assert observed["chunks"][0]["document_id"] == "bns"
    assert "Summarize the selected document" in observed["message"]
    assert events[0]["type"] == "chunk"
    assert events[-1]["type"] == "done"
    assert saved[-1][2] == "இந்த ஆவணம் குற்றங்களையும் அவற்றுக்கான தண்டனைகளையும் விளக்குகிறது."


def test_first_message_names_only_an_empty_conversation():
    from app.services import chat_service

    conversation = {
        "conversation_id": "conversation-1",
        "user_id": "user-1",
        "title": "New conversation",
    }

    class FakeConversations:
        updates = []

        def find_one(self, query):
            return conversation if query["conversation_id"] == conversation["conversation_id"] else None

        def update_one(self, query, update):
            self.updates.append(update)
            conversation.update(update["$set"])

    collection = FakeConversations()
    original_collection = chat_service.conversations_col
    chat_service.conversations_col = lambda: collection
    try:
        first_id = chat_service._get_or_create_conversation(
            "conversation-1", "user-1", "First question"
        )
        second_id = chat_service._get_or_create_conversation(
            "conversation-1", "user-1", "A follow-up question"
        )
    finally:
        chat_service.conversations_col = original_collection

    assert first_id == second_id == "conversation-1"
    assert conversation["title"] == "First question"
    assert len(collection.updates) == 1


def test_raw_llm_stream_yields_incremental_translation_chunks():
    import asyncio
    from app.services import llm

    async def fake_ollama_stream(*args, **kwargs):
        yield "தமிழ் "
        yield "மொழிபெயர்ப்பு"

    original_stream = llm.stream_ollama_chat
    llm.stream_ollama_chat = fake_ollama_stream
    try:
        async def collect():
            return [chunk async for chunk in llm.stream_raw("translate", "legal text")]

        chunks = asyncio.run(collect())
    finally:
        llm.stream_ollama_chat = original_stream

    assert chunks == ["தமிழ் ", "மொழிபெயர்ப்பு"]


def test_stream_translation_yields_and_caches_target_language():
    import asyncio
    from types import SimpleNamespace
    from app.database import mongodb
    from app.services import translator

    class FakeTranslations:
        def __init__(self):
            self.entries = {}

        def find_one(self, query):
            return self.entries.get(query["cache_key"])

        def update_one(self, query, update, upsert=False):
            self.entries[query["cache_key"]] = update["$set"]

    class FakeStream:
        calls = 0

        async def __call__(self, *args, **kwargs):
            self.calls += 1
            yield "தமிழ் "
            yield "மொழிபெயர்ப்பு"

    translations = FakeTranslations()
    stream = FakeStream()
    original_db = mongodb.get_db
    original_stream = translator.stream_raw
    mongodb.get_db = lambda: SimpleNamespace(translations=translations)
    translator.stream_raw = stream

    async def collect():
        first = [chunk async for chunk in translator.stream_translate_text("Legal text", "Tamil")]
        second = [chunk async for chunk in translator.stream_translate_text("Legal text", "Tamil")]
        return first, second

    try:
        first, second = asyncio.run(collect())
    finally:
        mongodb.get_db = original_db
        translator.stream_raw = original_stream

    assert first == ["தமிழ் ", "மொழிபெயர்ப்பு"]
    assert second == ["தமிழ் மொழிபெயர்ப்பு"]
    assert stream.calls == 1


def test_exact_tamil_answer_summarizes_only_requested_provision():
    import asyncio
    from app.services import chat_service, llm

    async def fake_answer(message, chunks, language, history):
        assert language == "Tamil"
        assert len(chunks) == 1
        assert chunks[0]["article"] == "21"
        yield "சரத்து 21 உயிர் மற்றும் தனிநபர் சுதந்திரத்தைப் பாதுகாக்கிறது."

    chunk = {
        "article": "21",
        "text": "A legal source text.",
        "document_id": "constitution",
        "document_name": "Constitution",
        "document_type": "constitution",
        "source_type": "actual_law",
        "chunk_id": "article-21",
        "child_index": 0,
        "page_start": 1,
        "page_end": 1,
    }
    originals = {
        "create": chat_service._get_or_create_conversation,
        "history": chat_service._recent_history,
        "save": chat_service._save_message,
        "retrieve": chat_service.retrieve,
        "answer": chat_service.llm.stream_answer,
    }
    saved_messages = []
    chat_service._get_or_create_conversation = lambda *args: "test-conversation"
    chat_service._recent_history = lambda *args: []
    chat_service._save_message = lambda *args: saved_messages.append(args)
    chat_service.retrieve = lambda message: {
        "mode": "exact",
        "chunks": [chunk, {**chunk, "article": "22", "chunk_id": "article-22"}],
        "intent": {"query_type": "article", "number": "21"},
    }
    chat_service.llm.stream_answer = fake_answer

    async def collect_events():
        return [event async for event in chat_service.stream_chat_message(
            message="அரசியலமைப்பு 21வது பிரிவு",
            conversation_id="test-conversation",
            language="English",
            user_id="test-user",
        )]

    try:
        events = asyncio.run(collect_events())
    finally:
        chat_service._get_or_create_conversation = originals["create"]
        chat_service._recent_history = originals["history"]
        chat_service._save_message = originals["save"]
        chat_service.retrieve = originals["retrieve"]
        chat_service.llm.stream_answer = originals["answer"]

    assert [event["text"] for event in events if event["type"] == "chunk"] == [
        "சரத்து 21 உயிர் மற்றும் தனிநபர் சுதந்திரத்தைப் பாதுகாக்கிறது."
    ]
    assert events[-1]["type"] == "done"
    assert saved_messages[-1][2] == "சரத்து 21 உயிர் மற்றும் தனிநபர் சுதந்திரத்தைப் பாதுகாக்கிறது."


def test_exact_retrieval_with_multilingual_queries():
    # Telugu query for Article 21 must route to exact match
    res_te = retrieve("ఆర్టికల్ 21 ఏమిటి?")
    assert res_te["mode"] == "exact"
    assert len(res_te["chunks"]) > 0
    assert "personal liberty" in res_te["chunks"][0]["text"].lower()

    # Hindi query for Article 21 must route to exact match
    res_hi = retrieve("अनुच्छेद 21 क्या है?")
    assert res_hi["mode"] == "exact"
    assert len(res_hi["chunks"]) > 0
    assert "personal liberty" in res_hi["chunks"][0]["text"].lower()

    # English query for Article 21
    res_en = retrieve("What is Article 21?")
    assert res_en["mode"] == "exact"
    assert len(res_en["chunks"]) > 0
    assert "personal liberty" in res_en["chunks"][0]["text"].lower()

    for number in ("9", "13", "15", "27", "47"):
        result = retrieve(f"Article {number} of the Constitution")
        assert result["mode"] == "exact"
        assert any(
            chunk.get("document_id") == "constitution" and chunk.get("article") == number
            for chunk in result["chunks"]
        )

    tamil_article_19 = retrieve("19வது சரத்து என்ன?")
    assert tamil_article_19["mode"] == "exact"
    assert any(
        chunk.get("document_id") == "constitution" and chunk.get("article") == "19"
        for chunk in tamil_article_19["chunks"]
    )

    tamil_law_article_19 = retrieve("சட்டம் 19")
    assert tamil_law_article_19["mode"] == "exact"
    assert all(chunk.get("document_id") == "constitution" for chunk in tamil_law_article_19["chunks"])
    assert any(chunk.get("article") == "19" for chunk in tamil_law_article_19["chunks"])


if __name__ == "__main__":
    tests = [
        test_indic_digit_normalization,
        test_multilingual_article_parsing,
        test_multilingual_section_and_rule_parsing,
        test_bharatiya_statutes_route_and_extract_plain_section_headings,
        test_constitution_parser_accepts_wrapped_article_titles,
        test_constitution_parser_ignores_toc_and_keeps_article_bodies_separate,
        test_legal_query_routing,
        test_script_and_language_detection,
        test_language_resolution_dynamics,
        test_hindi_help_question_uses_localized_chitchat,
        test_tamil_greeting_with_name_uses_localized_chitchat,
        test_llm_unavailable_message_is_localized,
        test_translation_fallback_stays_in_requested_language,
        test_general_chat_handles_unavailable_llm_in_tamil,
        test_document_summary_uses_only_selected_document_chunks,
        test_first_message_names_only_an_empty_conversation,
        test_raw_llm_stream_yields_incremental_translation_chunks,
        test_stream_translation_yields_and_caches_target_language,
        test_exact_tamil_answer_summarizes_only_requested_provision,
        test_exact_retrieval_with_multilingual_queries,
    ]
    passed = 0
    print("Running DOJ-RAG Multilingual Test Suite...")
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nResult: {passed}/{len(tests)} tests passed.")
    if passed != len(tests):
        exit(1)

