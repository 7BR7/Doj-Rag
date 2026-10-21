"""
Unit and integration tests for Intelligent Query Classification, Routing,
and Context Construction.

Covers:
1. General Questions -> No PDF retrieval, answered via LLM directly.
2. Legal Questions -> Routed to legal retrieval and grounded contexts.
3. PDF-Specific Questions -> Uses uploaded/selected document context with citation transparency.
4. Hybrid Questions -> Combines PDF context with broad statutory rules.
5. Multilingual Query Classification -> Works seamlessly across Hindi, Tamil, Kannada, and other supported Indian languages.
6. Citation Accuracy & Unsupported Claim Rejection -> Flags claims not present in retrieved context.
"""
import pytest
from app.rag.query_router import (
    classify_query,
    QUERY_TYPE_GENERAL,
    QUERY_TYPE_LEGAL,
    QUERY_TYPE_PDF_SPECIFIC,
    QUERY_TYPE_HYBRID
)
from app.rag.citation_verifier import verify_answer_citations


class TestIntelligentQueryRouter:
    """Test classification of incoming queries into architectural roles."""

    def test_general_query_classification_english(self):
        query = "What is the capital of France?"
        res = classify_query(query)
        assert res["route"] == QUERY_TYPE_GENERAL
        assert res["use_retrieval"] is False

    def test_general_chitchat_hindi(self):
        query = "नमस्ते, आप कैसे हैं?"
        res = classify_query(query)
        assert res["route"] == QUERY_TYPE_GENERAL
        assert res["use_retrieval"] is False

    def test_general_question_tamil(self):
        query = "வானிலை இன்று எப்படி இருக்கிறது?"
        res = classify_query(query)
        assert res["route"] == QUERY_TYPE_GENERAL
        assert res["use_retrieval"] is False

    def test_legal_query_constitution_hindi(self):
        query = "यदि किसी व्यक्ति के मौलिक अधिकारों का उल्लंघन होता है, तो क्या उपाय हैं?"
        res = classify_query(query)
        assert res["route"] == QUERY_TYPE_LEGAL
        assert res["use_retrieval"] is True

    def test_legal_query_constitution_kannada(self):
        query = "ಮೂಲಭೂತ ಹಕ್ಕುಗಳ ಉಲ್ಲಂಘನೆಗೆ ಯಾವ ಪರಿಹಾರಗಳಿವೆ?"
        res = classify_query(query)
        assert res["route"] == QUERY_TYPE_LEGAL
        assert res["use_retrieval"] is True

    def test_legal_query_tamil(self):
        query = "இந்திய அரசியலமைப்பில் உள்ள அடிப்படை உரிமைகள் என்ன?"
        res = classify_query(query)
        assert res["route"] == QUERY_TYPE_LEGAL
        assert res["use_retrieval"] is True

    def test_pdf_specific_query_with_doc_id(self):
        query = "What are the registration steps mentioned in this document?"
        res = classify_query(query, document_id="registration_user_manual")
        assert res["route"] == QUERY_TYPE_PDF_SPECIFIC
        assert res["use_retrieval"] is True

    def test_pdf_specific_query_with_phrasing(self):
        query = "इस दस्तावेज़ में क्या लिखा है?"
        res = classify_query(query, has_active_upload=True)
        assert res["route"] == QUERY_TYPE_PDF_SPECIFIC
        assert res["use_retrieval"] is True

    def test_hybrid_query(self):
        query = "Compare the bail terms in this document with BNSS bail provisions."
        res = classify_query(query, document_id="bail_doc_123")
        assert res["route"] == QUERY_TYPE_HYBRID
        assert res["use_retrieval"] is True


class TestCitationAndAnswerValidation:
    """Verifies that citations match retrieved sources and unsupported claims are flagged."""

    def test_valid_citation_verification(self):
        chunks = [
            {"document_name": "Constitution of India", "article": "21", "text": "No person shall be deprived of life or personal liberty except according to procedure established by law."},
            {"document_name": "Constitution of India", "article": "32", "text": "The right to move the Supreme Court for enforcement of rights is guaranteed."}
        ]
        answer = "Under Article 21, personal liberty is protected, and under Article 32, one can approach the Supreme Court."
        res = verify_answer_citations(answer, chunks)
        assert res["is_grounded"] is True
        assert len(res["unsupported_claims"]) == 0

    def test_unsupported_citation_detection(self):
        chunks = [
            {"document_name": "Constitution of India", "article": "21", "text": "Protection of life and personal liberty."}
        ]
        # Answer claims Article 356 and Section 420 which are not in the chunks
        answer = "Under Article 356 and Section 420, emergency can be imposed."
        res = verify_answer_citations(answer, chunks)
        assert res["is_grounded"] is False
        assert any("Article 356" in claim for claim in res["unsupported_claims"])
        assert any("Section 420" in claim for claim in res["unsupported_claims"])

    def test_empty_evidence_handling(self):
        res = verify_answer_citations("This is an ungrounded legal claim.", [])
        assert res["is_grounded"] is False
        assert res["grounding_score"] == 0.0
