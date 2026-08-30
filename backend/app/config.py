"""
Central configuration for DOJ-RAG backend.
All values are loaded from environment variables (.env), with sane local defaults.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/


class Settings:
    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "doj_rag")

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # Whisper
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # Embeddings
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )

    # Paths
    DATA_DIR: str = os.path.join(BASE_DIR, os.getenv("DATA_DIR", "data/legal_documents"))
    STORAGE_DIR: str = os.path.join(BASE_DIR, os.getenv("STORAGE_DIR", "storage"))
    FAISS_INDEX_PATH: str = os.path.join(STORAGE_DIR, "faiss.index")
    FAISS_META_PATH: str = os.path.join(STORAGE_DIR, "faiss_meta.pkl")
    BM25_PATH: str = os.path.join(STORAGE_DIR, "bm25.pkl")

    # CORS
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-only-change-this-secret-key-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days

    # Retrieval tuning
    TOP_K_BM25: int = 8
    TOP_K_FAISS: int = 8
    TOP_K_FINAL: int = 3  # fewer chunks -> smaller prompt -> faster LLM generation
    FUZZY_MATCH_THRESHOLD: int = 80  # RapidFuzz score threshold (0-100)

    # Chat context control
    MAX_HISTORY_MESSAGES: int = 4  # recent turns sent to the LLM (kept small for speed)

    # LLM generation speed tuning (see app/services/llm.py)
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "220"))
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "2048"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

    # Translation-specific model/settings (see app/services/translator.py).
    # Translation is a much simpler task than open-ended legal Q&A, so a
    # smaller, dedicated model here can be several times faster without
    # hurting translation quality. Defaults to OLLAMA_MODEL if not set, but
    # setting this to something small (e.g. "qwen2.5:1.5b") is the single
    # biggest speed lever for non-English answers.
    OLLAMA_TRANSLATE_MODEL: str = os.getenv("OLLAMA_TRANSLATE_MODEL", "") or None
    OLLAMA_TRANSLATE_NUM_PREDICT: int = int(os.getenv("OLLAMA_TRANSLATE_NUM_PREDICT", "300"))
    OLLAMA_TIMEOUT_SECONDS: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    SUPPORTED_LANGUAGES: dict = {}  # populated below after class definition, from app.i18n.messages


settings = Settings()
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.DATA_DIR, exist_ok=True)

# Single source of truth for supported languages lives in app.i18n.messages
# (display name -> speech locale / langdetect code), imported here so the
# rest of the codebase can keep using `settings.SUPPORTED_LANGUAGES`.
from app.i18n.messages import LANGUAGE_LOCALES  # noqa: E402
settings.SUPPORTED_LANGUAGES = {name: info["code"] for name, info in LANGUAGE_LOCALES.items()}
