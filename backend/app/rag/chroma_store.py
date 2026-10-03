"""
ChromaDB vector store adapter for DOJ-RAG.
ChromaDB is the primary vector database for document chunks and legal retrieval,
with support for incremental indexing, metadata filtering, and embedding storage.
"""
import os
import logging
from typing import List, Tuple, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings

logger = logging.getLogger("doj_rag.chroma_store")

_client = None
_collection = None
COLLECTION_NAME = "legal_chunks"


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        chroma_path = getattr(settings, "CHROMA_PERSIST_DIR", os.path.join(settings.STORAGE_DIR, "chroma_db"))
        os.makedirs(chroma_path, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
    return _client


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "DOJ-RAG Legal document chunks"}
        )
    return _collection


def add_chunks_to_chroma(
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
    batch_size: int = 250
):
    """
    Incrementally adds or updates document chunks in ChromaDB.
    """
    collection = get_collection()
    total = len(chunks)
    
    for i in range(0, total, batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_embeddings = embeddings[i : i + batch_size]
        
        ids = [c["chunk_id"] for c in batch_chunks]
        documents = [c.get("searchable_text", "") for c in batch_chunks]
        
        # Build clean metadata (Chroma requires primitive types: str, int, float, bool)
        metadatas = []
        for c in batch_chunks:
            meta = {
                "document_id": str(c.get("document_id") or ""),
                "document_name": str(c.get("document_name") or ""),
                "document_type": str(c.get("document_type") or ""),
                "source_type": str(c.get("source_type") or "actual_law"),
                "version": str(c.get("version") or "1"),
                "page_start": int(c.get("page_start") or 1),
                "page_end": int(c.get("page_end") or 1),
                "article": str(c.get("article") or ""),
                "section": str(c.get("section") or ""),
                "rule": str(c.get("rule") or ""),
            }
            metadatas.append(meta)
            
        collection.upsert(
            ids=ids,
            embeddings=batch_embeddings,
            documents=documents,
            metadatas=metadatas
        )
    logger.info(f"Upserted {total} chunks into ChromaDB collection '{COLLECTION_NAME}'.")


def search(
    query_embedding: Any,
    top_k: int = 8,
    where_filter: Optional[Dict[str, Any]] = None
) -> List[Tuple[str, float]]:
    """
    Searches ChromaDB vector store.
    Returns list of (chunk_id, similarity_score).
    """
    collection = get_collection()
    
    # query_embedding can be numpy array or list
    if hasattr(query_embedding, "tolist"):
        q_emb = query_embedding.tolist()
    else:
        q_emb = list(query_embedding)
        
    kwargs = {
        "query_embeddings": [q_emb],
        "n_results": top_k,
    }
    if where_filter:
        kwargs["where"] = where_filter
        
    try:
        results = collection.query(**kwargs)
    except Exception as e:
        logger.error(f"Error querying ChromaDB: {e}")
        return []
        
    hits = []
    if results and results.get("ids") and len(results["ids"]) > 0:
        ids = results["ids"][0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else []
        for idx, cid in enumerate(ids):
            # Chroma returns L2/cosine distance; convert to similarity score
            dist = distances[idx] if idx < len(distances) else 0.0
            # Higher is better: 1 / (1 + dist)
            score = 1.0 / (1.0 + max(0.0, float(dist)))
            hits.append((cid, score))
            
    return hits


def count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def delete_document_chunks(document_id: str):
    """Removes all chunks belonging to a document (used in incremental re-indexing)."""
    try:
        collection = get_collection()
        collection.delete(where={"document_id": document_id})
        logger.info(f"Deleted chunks for document {document_id} from ChromaDB.")
    except Exception as e:
        logger.error(f"Failed to delete document {document_id} from Chroma: {e}")
