"""
DOJ-RAG FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routes import chat, voice, conversations, auth, nlp, export, intelligence
from app.database.mongodb import MongoConnectionError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("doj_rag.main")

app = FastAPI(
    title="DOJ-RAG — AI Judiciary Legal Assistant",
    description="Local, free, RAG-powered legal chatbot for Indian legal documents.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(conversations.router)
app.include_router(nlp.router)
app.include_router(export.router)
app.include_router(intelligence.router)


@app.exception_handler(MongoConnectionError)
async def mongo_error_handler(request: Request, exc: MongoConnectionError):
    logger.error(f"MongoDB error: {exc}")
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
    )


@app.get("/")
def root():
    return {"status": "ok", "service": "DOJ-RAG backend"}


@app.get("/api/health")
def health():
    checks = {"api": "ok"}
    try:
        from app.database.mongodb import get_db
        get_db()
        checks["mongodb"] = "ok"
    except MongoConnectionError as e:
        checks["mongodb"] = f"error: {e}"

    try:
        import os
        from app.rag import chroma_store
        checks["chromadb"] = f"ok ({chroma_store.count()} chunks)"
        checks["faiss_index"] = "ok" if os.path.exists(settings.FAISS_INDEX_PATH) else "missing - run process_documents.py"
        checks["bm25_index"] = "ok" if os.path.exists(settings.BM25_PATH) else "missing - run process_documents.py"
    except Exception as e:
        checks["storage"] = f"error: {e}"

    # LLM provider status
    from app.services.llm import LLMProvider
    provider = LLMProvider.active_provider()
    model = LLMProvider.active_model()
    checks["llm_provider"] = provider
    checks["llm_model"] = model

    if provider == "groq":
        checks["groq"] = "configured"
    else:
        import requests as _req
        try:
            r = _req.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3)
            checks["ollama"] = "ok" if r.ok else f"error: HTTP {r.status_code}"
        except Exception as e:
            checks["ollama"] = f"unreachable: {e}"

    try:
        from app.nlp.knowledge_graph import get_graph
        G = get_graph()
        checks["knowledge_graph"] = f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
    except Exception as e:
        checks["knowledge_graph"] = f"error: {e}"

    return checks
