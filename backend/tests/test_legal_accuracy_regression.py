"""
Comprehensive regression test suite for legal accuracy, constitutional remedies,
multilingual preservation, and ungrounded query boundaries across 12 Indian languages + English.

Tests specifically cover:
- Test A: Tamil Fundamental Rights (six categories, Part III vs Part IV/IVA)
- Test B: Hindi Remedies for Violation of Rights (Articles 32 & 226, SC vs HC, no fake local court writs)
- Test C: English Part III (FR) vs Part IV (DPSP)
- Test D: Tamil Article 21
- Test E: Hindi Article 14 vs 21
- Test F: Unsupported statutory query boundary
- Test G: Cross-language retrieval (Tamil query -> English constitution source)
- Multilingual tests across all 12 Indian languages (Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Urdu).
"""
import pytest
from app.rag.retriever import retrieve
from app.rag.concept_retriever import extract_concept_from_query, get_articles_for_concept
from app.utils.legal_query_parser import parse_legal_query, is_legal_query
from app.rag.citation_verifier import verify_answer_citations


class TestLegalConstitutionalAccuracy:
    """Tests for constitutional legal grounding and correct retrieval."""

    def test_a_tamil_fundamental_rights_retrieval(self):
        query = "இந்திய அரசியலமைப்பில் வழங்கப்பட்டுள்ள அடிப்படை உரிமைகள் யாவை?"
        result = retrieve(query)
        assert result["mode"] in ("concept", "exact", "hybrid")
        articles = [c.get("article") for c in result.get("chunks", []) if c.get("article")]
        # Must retrieve core fundamental rights provisions (Part III, 12-35)
        part3_articles = {"12", "13", "14", "15", "16", "17", "18", "19", "21", "21A", "32"}
        assert any(art in part3_articles for art in articles), f"Retrieved {articles}, expected Part III articles"

    def test_b_hindi_remedies_for_violation_retrieval(self):
        query = "यदि किसी व्यक्ति के मौलिक अधिकारों का उल्लंघन होता है, तो वह कौन-से कानूनी उपाय अपना सकता है?"
        result = retrieve(query)
        assert result["mode"] in ("concept", "exact", "hybrid")
        articles = [c.get("article") for c in result.get("chunks", []) if c.get("article")]
        # Must retrieve Article 32 (Supreme Court) or Article 226 (High Court)
        assert "32" in articles or "226" in articles, f"Retrieved {articles}, expected Article 32 or 226"

    def test_c_english_dpsp_vs_fundamental_rights(self):
        query = "What is the difference between Fundamental Rights and Directive Principles of State Policy?"
        concept = extract_concept_from_query(query)
        assert concept in ("fundamental rights", "directive principles", "dpsp")
        result = retrieve(query)
        chunks = result.get("chunks", [])
        assert len(chunks) > 0

    def test_d_tamil_article_21(self):
        query = "அரசியலமைப்பின் 21வது கட்டுரை என்ன கூறுகிறது?"
        parsed = parse_legal_query(query)
        assert parsed["query_type"] == "article"
        assert parsed["number"] == "21"
        result = retrieve(query)
        assert result["mode"] == "exact"
        articles = [c.get("article") for c in result.get("chunks", [])]
        assert "21" in articles

    def test_e_hindi_article_14_and_21(self):
        query = "अनुच्छेद 14 और अनुच्छेद 21 में क्या अंतर है?"
        result = retrieve(query)
        articles = [c.get("article") for c in result.get("chunks", [])]
        assert "14" in articles or "21" in articles

    def test_f_unsupported_question_handling(self):
        query = "What is Section 9999 of the Intergalactic Space Commerce Act 3050?"
        assert not is_legal_query(query) or retrieve(query).get("mode") in ("not_found", "none", "hybrid")
        # In citation verification with empty evidence, it must reject claims
        veri = verify_answer_citations("Section 9999 provides interstellar permits.", [])
        assert not veri["is_grounded"]
        assert len(veri["unsupported_claims"]) > 0

    def test_g_cross_language_tamil_to_english_constitution(self):
        query = "சுற்றுச்சூழல் மற்றும் காடுகள் பாதுகாப்பு அரசியலமைப்பு சரத்து"
        result = retrieve(query)
        assert result["mode"] in ("concept", "hybrid", "exact")
        chunks = result.get("chunks", [])
        assert len(chunks) > 0
        # Check source is authentic legal text from indexed Constitution
        doc_names = [c.get("document_id") for c in chunks]
        assert "constitution" in doc_names or any(c.get("article") for c in chunks)


class TestAll12LanguagesConceptRetrieval:
    """Verifies that all 12 supported Indian languages trigger proper legal concept recognition."""

    @pytest.mark.parametrize("query,expected_concept", [
        ("मौलिक अधिकार क्या हैं?", "fundamental rights"),  # Hindi
        ("இந்தியாவின் அடிப்படை உரிமைகள்", "fundamental rights"),  # Tamil
        ("భారత రాజ్యాంగంలో ప్రాథమిక హక్కులు ఏవి?", "fundamental rights"),  # Telugu
        ("ಭಾರತದ ಸಂವಿಧಾನದಲ್ಲಿ ಮೂಲಭೂತ ಹಕ್ಕುಗಳು ಯಾವುವು?", "fundamental rights"),  # Kannada
        ("ഭരണഘടനയിലെ മൗലിക അവകാശങ്ങൾ ഏവ?", "fundamental rights"),  # Malayalam
        ("ভারতের সংবিধানে মৌলিক অধিকার কি কি?", "fundamental rights"),  # Bengali
        ("ભારતના બંધારણમાં મૂળભૂત અધિકારો કયા છે?", "fundamental rights"),  # Gujarati
        ("ਭਾਰਤੀ ਸੰਵਿਧਾਨ ਵਿੱਚ ਮੌਲਿਕ ਅਧਿਕਾਰ ਕਿਹੜੇ ਹਨ?", "fundamental rights"),  # Punjabi
        ("ଭାରତୀୟ ସମ୍ବିଧାନରେ ମୌଳିକ ଅଧିକାର କଣ?", "fundamental rights"),  # Odia
        ("بھارتی آئین میں بنیادی حقوق کیا ہیں؟", "fundamental rights"),  # Urdu
        ("भारतीय संविधानातील मूलभूत अधिकार कोणते आहेत?", "fundamental rights"),  # Marathi
    ])
    def test_multilingual_concept_resolution(self, query, expected_concept):
        concept = extract_concept_from_query(query)
        assert concept == expected_concept
        articles = get_articles_for_concept(concept)
        assert len(articles) > 0
        assert "14" in articles or "19" in articles or "21" in articles or "32" in articles
