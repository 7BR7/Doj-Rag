"""
Central configuration for DOJ-RAG backend.
All values are loaded from environment variables (.env), with sane local defaults.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Enforce offline mode for Hugging Face so local SentenceTransformers never stall on HTTPS retries
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

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
    TOP_K_FINAL: int = int(os.getenv("TOP_K_FINAL", "2"))  # 2 chunks -> compact prompt -> 2.5x faster LLM generation
    FUZZY_MATCH_THRESHOLD: int = 80  # RapidFuzz score threshold (0-100)

    # Chat context control
    MAX_HISTORY_MESSAGES: int = 4  # recent turns sent to the LLM (kept small for speed)

    # LLM generation speed tuning (see app/services/llm.py)
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "140"))
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "1024"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "60m")

    # Translation-specific model/settings (see app/services/translator.py).
    OLLAMA_TRANSLATE_MODEL: str = os.getenv("OLLAMA_TRANSLATE_MODEL", "") or None
    OLLAMA_TRANSLATE_NUM_PREDICT: int = int(os.getenv("OLLAMA_TRANSLATE_NUM_PREDICT", "200"))

    # For general/hybrid questions in a non-English language: True (default)
    # generates the answer directly in that language in ONE LLM call - the
    # fastest option. False generates in English first, then makes a SECOND
    # call to translate - slower (roughly double the LLM time) but can be
    # more reliable for languages/models where direct non-English
    # generation is noticeably weaker. Speed is the default priority here.
    HYBRID_SINGLE_PASS: bool = os.getenv("HYBRID_SINGLE_PASS", "true").lower() != "false"
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
