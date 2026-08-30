#!/usr/bin/env python3
"""
Test script covering the required test cases (see README section "Testing").
Run after process_documents.py has built the indexes and MongoDB is populated.

Usage:
    cd backend
    python scripts/test_retrieval.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.retriever import retrieve


def check(name, message, expect_mode, expect_contains=None):
    print(f"\n=== {name} ===")
    print(f"Query: {message}")
    result = retrieve(message)
    print(f"Mode: {result['mode']}")

    passed = result["mode"] == expect_mode
    if result["mode"] in ("exact", "suggested", "hybrid") and result["chunks"]:
        top_text = result["chunks"][0]["text"][:150]
        print(f"Top chunk: {top_text}...")
        if expect_contains:
            passed = passed and (expect_contains.lower() in result["chunks"][0]["text"].lower())
    elif result["mode"] == "clarify":
        print(f"Suggestions: {result['suggestions']}")

    print("PASS" if passed else "FAIL")
    return passed


def main():
    results = []

    # Test 1: Article 21 must return actual legal text, not TOC
    results.append(check(
        "Test 1 - Article 21", "What is Article 21?",
        expect_mode="exact", expect_contains="personal liberty"
    ))

    # Test 2: Article 21A
    results.append(check(
        "Test 2 - Article 21A", "Explain Article 21A",
        expect_mode="exact", expect_contains="education"
    ))

    # Test 3: Invalid article -> clarification or not_found, never a wrong hallucinated article.
    # NOTE: Article 212 genuinely exists in the Constitution ("Courts not to inquire
    # into proceedings of the Legislature"), so it is NOT a valid invalid-reference
    # test case. Article 396 does not exist (the Constitution has 395 Articles),
    # making it a correct choice for this test.
    results.append(check(
        "Test 3 - Invalid Article 396", "Explain Article 396",
        expect_mode="clarify"
    ))

    # Test 4: General hybrid question
    results.append(check(
        "Test 4 - General question", "What are fundamental rights?",
        expect_mode="hybrid"
    ))

    print(f"\n{sum(results)}/{len(results)} tests passed.")


if __name__ == "__main__":
    main()
