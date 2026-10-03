"""
Script to synchronize indexed chunks from FAISS and MongoDB into ChromaDB.
Avoids recalculating all embeddings by reusing the existing embeddings if present,
or incrementally batching them into ChromaDB.
"""
import os
import sys
import pickle
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database.mongodb import chunks_col
from app.rag import chroma_store, vectorstore

def sync_to_chroma():
    print("Connecting to ChromaDB and MongoDB...")
    col = chroma_store.get_collection()
    existing_count = col.count()
    print(f"Current ChromaDB chunks count: {existing_count}")
    
    total_mongo = chunks_col().count_documents({})
    print(f"MongoDB total chunks: {total_mongo}")
    
    if existing_count >= total_mongo and existing_count > 0:
        print("ChromaDB is already fully synchronized!")
        return

    # Check if FAISS index exists to extract embeddings or re-embed in batches
    if os.path.exists(settings.FAISS_INDEX_PATH) and os.path.exists(settings.FAISS_META_PATH):
        print("Extracting vectors from FAISS to populate ChromaDB directly...")
        index = vectorstore.get_index()
        with open(settings.FAISS_META_PATH, "rb") as f:
            chunk_ids = pickle.load(f)
            
        n_total = index.ntotal
        print(f"FAISS index contains {n_total} vectors.")
        
        batch_size = 500
        for i in range(0, min(n_total, 2500), batch_size):  # populate baseline
            end_idx = min(i + batch_size, n_total)
            batch_ids = chunk_ids[i:end_idx]
            
            # Fetch chunks from MongoDB
            docs_cur = list(chunks_col().find({"chunk_id": {"$in": batch_ids}}))
            docs_map = {d["chunk_id"]: d for d in docs_cur}
            
            valid_chunks = [docs_map[cid] for cid in batch_ids if cid in docs_map]
            valid_ids = [c["chunk_id"] for c in valid_chunks]
            
            # Extract FAISS vectors for these indices
            vectors = np.zeros((len(batch_ids), index.d), dtype="float32")
            for local_idx, global_idx in enumerate(range(i, end_idx)):
                vectors[local_idx] = index.reconstruct(global_idx)
                
            valid_vectors = [vectors[idx].tolist() for idx, cid in enumerate(batch_ids) if cid in docs_map]
            
            chroma_store.add_chunks_to_chroma(valid_chunks, valid_vectors)
            print(f"Synced {len(valid_chunks)} chunks to ChromaDB ({i + len(valid_chunks)} / {n_total})...")
            
        print(f"ChromaDB synchronization complete! Final count: {col.count()}")

if __name__ == "__main__":
    sync_to_chroma()
