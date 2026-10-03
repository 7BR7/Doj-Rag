"""
ML-based Intent Classification and Query Expansion module.
Uses TF-IDF + Logistic Regression / Linear SVM trained on curated legal query patterns,
with rule-based fallback and semantic legal query expansion.
"""
import re
import os
import pickle
import logging
from typing import List, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from app.config import settings

logger = logging.getLogger("doj_rag.intent_classifier")

# 14 distinct legal intent classes as required
INTENT_CLASSES = [
    "SECTION_LOOKUP",
    "ARTICLE_LOOKUP",
    "DOCUMENT_SUMMARY",
    "LEGAL_DEFINITION",
    "CASE_LOOKUP",
    "COURT_LOOKUP",
    "AMENDMENT_QUERY",
    "COMPARISON_QUERY",
    "DATE_QUERY",
    "PROCEDURE_QUERY",
    "GENERAL_DOCUMENT_QUERY",
    "FOLLOW_UP_QUERY",
    "MULTI_DOCUMENT_QUERY",
    "EXPLANATION_QUERY"
]

TRAINING_DATA: List[Tuple[str, str]] = [
    # SECTION_LOOKUP
    ("What does Section 12 say?", "SECTION_LOOKUP"),
    ("Read section 302 of BNS", "SECTION_LOOKUP"),
    ("Explain Section 4 of the filing user manual", "SECTION_LOOKUP"),
    ("Details of sec 437 in bnss", "SECTION_LOOKUP"),
    ("Show me Section 65B of Evidence Act", "SECTION_LOOKUP"),
    ("Section 10 provisions and clauses", "SECTION_LOOKUP"),
    ("What is in sec 12?", "SECTION_LOOKUP"),

    # ARTICLE_LOOKUP
    ("What is Article 21?", "ARTICLE_LOOKUP"),
    ("Explain Article 14 of Indian Constitution", "ARTICLE_LOOKUP"),
    ("Tell me about Article 19 freedom of speech", "ARTICLE_LOOKUP"),
    ("Article 32 constitutional remedies", "ARTICLE_LOOKUP"),
    ("Provisions of Article 21A right to education", "ARTICLE_LOOKUP"),
    ("Article 370 background", "ARTICLE_LOOKUP"),

    # DOCUMENT_SUMMARY
    ("Summarize the BNS Act", "DOCUMENT_SUMMARY"),
    ("Give me an overview of the CIS 3.0 manual", "DOCUMENT_SUMMARY"),
    ("What is the main purpose of this document?", "DOCUMENT_SUMMARY"),
    ("Executive summary of NALSA guidelines", "DOCUMENT_SUMMARY"),
    ("Briefly summarize the Constitution of India", "DOCUMENT_SUMMARY"),

    # LEGAL_DEFINITION
    ("What is the legal definition of bail?", "LEGAL_DEFINITION"),
    ("Define electronic record under legal terms", "LEGAL_DEFINITION"),
    ("What does cognizable offence mean?", "LEGAL_DEFINITION"),
    ("Define public servant in Bharatiya Nyaya Sanhita", "LEGAL_DEFINITION"),
    ("Meaning of Habeas Corpus", "LEGAL_DEFINITION"),

    # CASE_LOOKUP
    ("Which case decided the privacy right?", "CASE_LOOKUP"),
    ("Search for Kesavananda Bharati judgment", "CASE_LOOKUP"),
    ("Supreme court ruling in Maneka Gandhi", "CASE_LOOKUP"),
    ("Case law regarding Section 302", "CASE_LOOKUP"),

    # COURT_LOOKUP
    ("Jurisdiction of Supreme Court under Article 131", "COURT_LOOKUP"),
    ("Powers of the High Court in writ petitions", "COURT_LOOKUP"),
    ("Can district court grant anticipatory bail?", "COURT_LOOKUP"),

    # AMENDMENT_QUERY
    ("Was Section 12 amended?", "AMENDMENT_QUERY"),
    ("When was Article 21A inserted into the Constitution?", "AMENDMENT_QUERY"),
    ("History of 44th Amendment Act", "AMENDMENT_QUERY"),
    ("What changed in the recent amendment to this act?", "AMENDMENT_QUERY"),
    ("Amendments made to criminal procedure code", "AMENDMENT_QUERY"),

    # COMPARISON_QUERY
    ("Compare Article 14 and Article 21", "COMPARISON_QUERY"),
    ("Difference between BNS and IPC", "COMPARISON_QUERY"),
    ("How does Section 12 differ between version 1 and version 2?", "COMPARISON_QUERY"),
    ("Compare bail provisions in BNSS versus CrPC", "COMPARISON_QUERY"),

    # DATE_QUERY
    ("When did BNS come into force?", "DATE_QUERY"),
    ("What was the enactment date of the Constitution of India?", "DATE_QUERY"),
    ("Effective date of the criminal amendment rules", "DATE_QUERY"),
    ("When was this user manual published?", "DATE_QUERY"),

    # PROCEDURE_QUERY
    ("How to file an e-filing petition online?", "PROCEDURE_QUERY"),
    ("What are the steps to submit an ePay transaction?", "PROCEDURE_QUERY"),
    ("Procedure for under trial review committee release", "PROCEDURE_QUERY"),
    ("Process for filing legal aid defense counsel application", "PROCEDURE_QUERY"),

    # GENERAL_DOCUMENT_QUERY
    ("Which documents discuss electronic records?", "GENERAL_DOCUMENT_QUERY"),
    ("List all guidelines regarding juvenile justice in the repository", "GENERAL_DOCUMENT_QUERY"),
    ("What documents cover legal awareness camps?", "GENERAL_DOCUMENT_QUERY"),

    # FOLLOW_UP_QUERY
    ("Explain it in simple words", "FOLLOW_UP_QUERY"),
    ("What are its exceptions?", "FOLLOW_UP_QUERY"),
    ("Can you tell me more about that?", "FOLLOW_QUERY" if "FOLLOW_QUERY" in INTENT_CLASSES else "FOLLOW_UP_QUERY"),
    ("Why did you give this answer?", "FOLLOW_UP_QUERY"),
    ("Show the sources for your answer", "FOLLOW_UP_QUERY"),

    # MULTI_DOCUMENT_QUERY
    ("Compare how relevant documents address electronic records", "MULTI_DOCUMENT_QUERY"),
    ("Across all acts, what is stated about women prisoners?", "MULTI_DOCUMENT_QUERY"),
    ("Cross reference legal aid in NALSA and CIS manuals", "MULTI_DOCUMENT_QUERY"),

    # EXPLANATION_QUERY
    ("Explain Section 12 in simple words", "EXPLANATION_QUERY"),
    ("Explain this section for a normal citizen", "EXPLANATION_QUERY"),
    ("Simplify the language of Article 21", "EXPLANATION_QUERY")
]

MODEL_PATH = os.path.join(settings.STORAGE_DIR, "intent_classifier.pkl")
_model = None
_vectorizer = None


def train_classifier():
    """Trains TF-IDF + LogisticRegression on the labeled legal intent dataset."""
    global _model, _vectorizer
    texts, labels = zip(*TRAINING_DATA)
    
    vec = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, max_features=500)
    X = vec.fit_transform(texts)
    
    clf = LogisticRegression(C=5.0, max_iter=200, random_state=42)
    clf.fit(X, labels)
    
    _vectorizer = vec
    _model = clf
    
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": clf, "vectorizer": vec}, f)
    logger.info("Trained and saved legal intent classifier model.")


def load_classifier():
    global _model, _vectorizer
    if _model is not None and _vectorizer is not None:
        return _model, _vectorizer
        
    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
                _model = data["model"]
                _vectorizer = data["vectorizer"]
                return _model, _vectorizer
        except Exception:
            pass
            
    train_classifier()
    return _model, _vectorizer


def classify_intent(query: str) -> Dict[str, Any]:
    """
    Predicts intent using the ML classifier, with fallback to rule heuristics.
    """
    model, vectorizer = load_classifier()
    X = vectorizer.transform([query])
    pred = model.predict(X)[0]
    probs = model.predict_proba(X)[0]
    confidence = float(max(probs))
    
    # Specific rule overrides for high-precision exact queries
    lowered = query.lower()
    if re.search(r"\b(article|art\.?)\s*\d+[a-z]?\b", lowered):
        pred = "ARTICLE_LOOKUP"
        confidence = 0.95
    elif re.search(r"\b(section|sec\.?)\s*\d+[a-z]?\b", lowered):
        pred = "SECTION_LOOKUP"
        confidence = 0.95
    elif "amend" in lowered:
        pred = "AMENDMENT_QUERY"
    elif "compare" in lowered or "difference between" in lowered:
        pred = "COMPARISON_QUERY"
    elif "why did you" in lowered or "show the sources" in lowered:
        pred = "FOLLOW_UP_QUERY"
        
    return {
        "intent": pred,
        "confidence": round(confidence, 3),
        "query": query
    }


def expand_query(query: str) -> List[str]:
    """
    Generates domain-aware query expansions without shifting semantic meaning.
    Example:
      'What does section 12 say?' ->
      ['section 12', 'section 12 provision', 'section 12 requirements', 'section 12 exceptions']
    """
    expansions = [query]
    
    sec_match = re.search(r"\bsection\s+(\d+[a-z]?)\b", query, re.IGNORECASE)
    if sec_match:
        s_num = sec_match.group(1)
        expansions.extend([
            f"Section {s_num}",
            f"Section {s_num} provision",
            f"Section {s_num} requirements",
            f"Section {s_num} exceptions"
        ])
        
    art_match = re.search(r"\barticle\s+(\d+[a-z]?)\b", query, re.IGNORECASE)
    if art_match:
        a_num = art_match.group(1)
        expansions.extend([
            f"Article {a_num}",
            f"Article {a_num} constitution",
            f"Article {a_num} fundamental rights",
            f"Article {a_num} scope"
        ])
        
    if "electronic record" in query.lower():
        expansions.extend([
            "electronic evidence",
            "digital record",
            "section 65B electronic record"
        ])
        
    # Return unique expansions
    return list(dict.fromkeys(expansions))
