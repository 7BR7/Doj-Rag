#!/usr/bin/env python3
"""
Document processing pipeline. Run this after dropping legal PDFs into
backend/data/legal_documents/.

Usage:
    cd backend
    python scripts/process_documents.py

This will:
  1. Load and detect the type of every PDF
  2. Clean headers/footers/page-numbers/OCR noise
  3. Route to the correct structure-aware parser
  4. Build structure-aware chunks with metadata
  5. Store document + chunk metadata in MongoDB
  6. Generate embeddings and build the FAISS index
  7. Build the BM25 index
"""
import os
import sys
import glob
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database.mongodb import documents_col, chunks_col, now, MongoConnectionError
from app.rag.document_loader import load_document
from app.rag.parser_router import route_and_parse
from app.rag.chunker import build_chunks
from app.rag.embeddings import embed_texts
from app.rag import vectorstore, bm25_search
from app.utils.text_cleaner import clean_document_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("process_documents")


def process_all():
    pdf_paths = sorted(glob.glob(os.path.join(settings.DATA_DIR, "*.pdf")))
    if not pdf_paths:
        logger.warning(
            f"No PDFs found in {settings.DATA_DIR}. "
            "Add your ~25 legal PDFs there and re-run this script."
        )
        return

    try:
        documents_col()
    except MongoConnectionError as e:
        logger.error(str(e))
        sys.exit(1)

    all_chunks = []

    for pdf_path in pdf_paths:
        filename = os.path.basename(pdf_path)
        logger.info(f"Processing {filename} ...")

        document = load_document(pdf_path)
        document["pages"] = clean_document_pages(document["pages"])
        document["document_name"] = os.path.splitext(filename)[0].replace("_", " ").title()

        units = route_and_parse(document)
        logger.info(f"  -> detected type: {document['document_type']}, parsed {len(units)} structural units")

        if not units:
            logger.warning(f"  !! No structural units extracted from {filename}. Skipping.")
            continue

        chunks = build_chunks(units)
        logger.info(f"  -> produced {len(chunks)} chunks")

        documents_col().update_one(
            {"document_id": document["document_id"]},
            {"$set": {
                "document_id": document["document_id"],
                "document_name": document["document_name"],
                "filename": filename,
                "document_type": document["document_type"],
                "num_units": len(units),
                "num_chunks": len(chunks),
                "processed_at": now(),
            }},
            upsert=True,
        )

        for c in chunks:
            chunks_col().update_one({"chunk_id": c["chunk_id"]}, {"$set": c}, upsert=True)

        all_chunks.extend(chunks)

    if not all_chunks:
        logger.error("No chunks were produced from any document. Aborting index build.")
        return

    logger.info(f"Total chunks across all documents: {len(all_chunks)}")
    logger.info("Generating embeddings (this may take a few minutes on CPU)...")

    texts = [c["searchable_text"] for c in all_chunks]
    chunk_ids = [c["chunk_id"] for c in all_chunks]

    embeddings = embed_texts(texts)
    vectorstore.build_index(embeddings, chunk_ids)
    bm25_search.build_bm25(texts, chunk_ids)

    logger.info("Done. FAISS + BM25 indexes built and saved to storage/.")
    logger.info("You can now start the backend: uvicorn app.main:app --reload")


if __name__ == "__main__":
    process_all()
