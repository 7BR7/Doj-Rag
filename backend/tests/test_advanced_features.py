"""
Automated unit & integration tests for Advanced NLP, Groq LLM configuration,
Knowledge Graph, and Export functionalities.
"""
from app.nlp.nlp_pipeline import (
    extract_legal_entities,
    detect_intent,
    decompose_query,
    normalize_query,
)
from app.nlp.knowledge_graph import get_graph, get_related_provisions, get_graph_summary
from app.config import settings
from app.services.llm import LLMProvider


def test_legal_ner_extraction():
    text = "Under the Protection of Human Rights Act 1993, the Supreme Court held that Article 21 and Section 302 apply to Fundamental Rights."
    entities = extract_legal_entities(text)
    assert "Supreme Court" in entities["courts"]
    assert "21" in entities["articles"]
    assert "302" in entities["sections"]
    assert any("Human Rights Act" in act for act in entities["acts"])
    assert any("Fundamental Right" in c for c in entities["concepts"])


def test_intent_detection():
    assert detect_intent("What is Article 21 of the Indian Constitution?") == "DEFINITION"
    assert detect_intent("What is the difference between Article 14 and Article 19?") == "COMPARISON"
    assert detect_intent("How to file a writ petition under Article 32?") == "PROCEDURE"
    assert detect_intent("What is the punishment or penalty for violation?") == "PENALTY"
    assert detect_intent("When was the 86th amendment enacted?") == "TIMELINE"
    assert detect_intent("Do citizens have the fundamental right to freedom of speech?") == "RIGHTS"


def test_query_decomposition():
    # Multi-article query should decompose
    q = "What are Article 14 and Article 21?"
    sub_queries = decompose_query(q)
    assert len(sub_queries) == 2
    assert any("Article 14" in sq for sq in sub_queries)
    assert any("Article 21" in sq for sq in sub_queries)

    # Single atomic query should remain 1 query
    single = "What is Article 19?"
    assert decompose_query(single) == [single]


def test_query_normalization():
    # Abbreviation expansion
    assert "First Information Report" in normalize_query("How to lodge an FIR?")
    assert "Public Interest Litigation" in normalize_query("Can I file a PIL in SC?")
    assert "Supreme Court" in normalize_query("Can I file a PIL in SC?")


def test_knowledge_graph_connectivity():
    G = get_graph()
    assert G.number_of_nodes() > 10
    assert G.number_of_edges() > 10

    # Test related provisions lookup
    related = get_related_provisions("Article", "21")
    labels = [r["label"] for r in related]
    identifiers = [r["identifier"] for r in related]
    # Article 21 has relationships to Article 14, Article 19, or Fundamental Rights
    assert any("14" in i or "19" in i or "Fundamental" in l for i, l in zip(identifiers, labels))


def test_llm_provider_selection():
    # Verify fallback or auto selection logic
    provider = LLMProvider.active_provider()
    model = LLMProvider.active_model()
    assert provider in ("groq", "ollama")
    assert len(model) > 0
    if settings.GROQ_API_KEY:
        assert provider == "groq"
    else:
        assert provider == "ollama"
