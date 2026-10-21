"""
Regression test suite for legal fact-checking and constitutional accuracy.

Specifically tests:
1. Part III: Fundamental Rights (Articles 12 to 35).
2. Part IV: Directive Principles of State Policy (Articles 36 to 51).
3. Article 37: Explicit non-enforceability of DPSP in any court of law.
4. Detection and automated correction of legal misconceptions (e.g. DPSP enforceability, property right as fundamental right, local court writs).
5. Grounded vs ungrounded citation validation.
"""
import pytest
from app.rag.fact_checker import fact_check_legal_claims, PART_III_RANGE, PART_IV_RANGE
from app.rag.retriever import retrieve
from app.database.mongodb import chunks_col


class TestConstitutionalPartBoundaries:
    """Verifies retrieval and factual boundaries for Parts III, IV, and Article 37."""

    def test_part_iii_range_definitions(self):
        """Fundamental Rights must span Articles 12-35."""
        assert "12" in PART_III_RANGE
        assert "14" in PART_III_RANGE
        assert "19" in PART_III_RANGE
        assert "21" in PART_III_RANGE
        assert "21A" in PART_III_RANGE
        assert "32" in PART_III_RANGE
        assert "35" in PART_III_RANGE
        assert "36" not in PART_III_RANGE
        assert "51A" not in PART_III_RANGE

    def test_part_iv_range_definitions(self):
        """Directive Principles of State Policy must span Articles 36-51."""
        assert "36" in PART_IV_RANGE
        assert "37" in PART_IV_RANGE
        assert "39A" in PART_IV_RANGE
        assert "44" in PART_IV_RANGE
        assert "48A" in PART_IV_RANGE
        assert "51" in PART_IV_RANGE
        assert "51A" not in PART_IV_RANGE
        assert "14" not in PART_IV_RANGE

    def test_article_37_retrieval_and_text(self):
        """Article 37 explicitly states provisions shall not be enforceable by any court."""
        res = retrieve("What does Article 37 say?")
        assert res["mode"] == "exact"
        chunks = res.get("chunks", [])
        assert len(chunks) > 0
        art37_text = " ".join(c.get("text", "") for c in chunks).lower()
        assert "not be enforceable by any court" in art37_text or "fundamental in the governance" in art37_text


class TestLegalFactCheckingEngine:
    """Tests the post-generation legal claim and fact-checking validator."""

    def test_intercept_dpsp_enforceability_claim(self):
        """Falsely claiming Directive Principles can be enforced in court must be flagged and corrected."""
        wrong_answer = "The Directive Principles of State Policy are enforceable by court under Part IV."
        check = fact_check_legal_claims(wrong_answer, [])
        assert check["is_factually_accurate"] is False
        assert any("Article 37" in err for err in check["factual_errors"])
        assert "Article 37" in check["corrected_text"]

    def test_intercept_property_fundamental_right_claim(self):
        """Claiming Right to Property is still a Fundamental Right must be flagged and corrected."""
        wrong_answer = "Right to property under Article 300A is a fundamental right of every citizen."
        check = fact_check_legal_claims(wrong_answer, [])
        assert check["is_factually_accurate"] is False
        assert any("44th" in err for err in check["factual_errors"])
        assert "300A" in check["corrected_text"]

    def test_intercept_local_court_writ_claim(self):
        """Claiming a local district court issues constitutional writs must be flagged and corrected."""
        wrong_answer = "You can approach the local district court to issue writs under Article 32 or Article 226."
        check = fact_check_legal_claims(wrong_answer, [])
        assert check["is_factually_accurate"] is False
        assert any("Supreme Court" in err or "High Court" in err for err in check["factual_errors"])

    def test_valid_grounded_legal_claims(self):
        """A correct legal claim grounded in retrieved evidence must pass with no errors."""
        chunks = [
            {"document_name": "Constitution of India", "article": "21", "text": "No person shall be deprived of life or personal liberty except according to procedure established by law."},
            {"document_name": "Constitution of India", "article": "32", "text": "The right to move the Supreme Court for enforcement of rights conferred by Part III is guaranteed."}
        ]
        accurate_answer = (
            "Article 21 protects the right to life and personal liberty under Part III. "
            "Under Article 32, an individual can approach the Supreme Court for enforcement of Fundamental Rights."
        )
        check = fact_check_legal_claims(accurate_answer, chunks)
        assert check["is_factually_accurate"] is True
        assert len(check["factual_errors"]) == 0
        assert "21" in check["verified_articles"]
        assert "32" in check["verified_articles"]
