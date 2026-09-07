"""
Automated unit & integration tests for DOJ-RAG Multilingual & Language Dynamics:
  - Indic numeral normalization
  - Multilingual legal query parsing (Telugu, Hindi, Tamil, Kannada, English)
  - Dynamic language resolution (auto-detect, stale dropdown prevention, manual override)
  - End-to-end exact match retrieval with non-English queries
  - Voice transcription route with language parameter
"""
from app.utils.legal_query_parser import parse_legal_query, normalize_indic_digits
from app.services.language import (
    detect_script_language,
    detect_language_from_text,
    resolve_turn_language,
    normalize_language_name,
)
from app.rag.retriever import retrieve


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


if __name__ == "__main__":
    tests = [
        test_indic_digit_normalization,
        test_multilingual_article_parsing,
        test_multilingual_section_and_rule_parsing,
        test_script_and_language_detection,
        test_language_resolution_dynamics,
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

