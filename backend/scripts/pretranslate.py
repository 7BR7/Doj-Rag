#!/usr/bin/env python3
"""
Pre-warms the translation cache so end users never pay the LLM-translation
cost live. Run this once per language you expect people to actually use -
after this, every "What is Article 21?" style exact-match answer in that
language is served straight from the MongoDB cache (same speed as English).

Usage:
    cd backend
    python scripts/pretranslate.py --language Hindi
    python scripts/pretranslate.py --language Tamil --language Telugu
    python scripts/pretranslate.py --all         # every supported language

This can take a while the FIRST time (one LLM call per Article/Section/Rule
per language) - that cost is meant to happen here, offline, once, instead of
live in front of a waiting user. Safe to re-run: already-cached translations
are skipped.
"""
import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database.mongodb import chunks_col, MongoConnectionError
from app.services.chat_service import _format_direct_answer  # reuse the exact same formatting as live traffic
from app.services.translator import translate_text
from app.i18n.messages import LANGUAGE_LOCALES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pretranslate")


def _group_chunks_by_reference():
    """Group chunks the same way the live exact-match path does: one entry
    per Article/Section/Rule (all its child chunks together), since that's
    the unit that actually gets translated and cached at request time."""
    groups = {}
    for c in chunks_col().find({"source_type": "actual_law"}):
        key = (c["document_id"], c.get("article"), c.get("section"), c.get("rule"))
        if key[1] is None and key[2] is None and key[3] is None:
            continue  # skip generic/paragraph chunks with no clean identifier
        groups.setdefault(key, []).append(c)
    for key in groups:
        groups[key].sort(key=lambda c: c.get("child_index", 0))
    return groups


def pretranslate(languages):
    try:
        groups = _group_chunks_by_reference()
    except MongoConnectionError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"Found {len(groups)} Article/Section/Rule references to translate.")
    total = len(groups) * len(languages)
    done = 0

    for language in languages:
        logger.info(f"--- Translating into {language} ---")
        for key, chunk_group in groups.items():
            answer = _format_direct_answer(chunk_group)
            translate_text(answer, language)  # caches as a side effect
            done += 1
            if done % 25 == 0:
                logger.info(f"  {done}/{total} done")

    logger.info(f"Done. {total} (reference, language) pairs are now warm in the cache.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", action="append", default=[],
                         help="Language to warm (repeatable), e.g. --language Hindi --language Tamil")
    parser.add_argument("--all", action="store_true", help="Warm every supported language")
    args = parser.parse_args()

    if args.all:
        languages = [lang for lang in LANGUAGE_LOCALES if lang != "English"]
    elif args.language:
        unknown = [l for l in args.language if l not in LANGUAGE_LOCALES]
        if unknown:
            print(f"Unknown language(s): {unknown}. Supported: {list(LANGUAGE_LOCALES)}")
            sys.exit(1)
        languages = args.language
    else:
        parser.print_help()
        sys.exit(1)

    pretranslate(languages)
