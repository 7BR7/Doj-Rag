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

    # Ollama (local LLM - fallback when Groq key is not set)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # Whisper (speech-to-text)
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
    KNOWLEDGE_GRAPH_PATH: str = os.path.join(STORAGE_DIR, "knowledge_graph.pkl")

    # CORS
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-only-change-this-secret-key-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days

    # Retrieval tuning
    TOP_K_BM25: int = 8
    TOP_K_FAISS: int = 8
    # With Groq (fast cloud LLM), we can afford more context for higher quality answers.
    # With Ollama (slow CPU), fewer chunks = faster generation. Both paths respect this.
    TOP_K_FINAL: int = int(os.getenv("TOP_K_FINAL", "3"))
    FUZZY_MATCH_THRESHOLD: int = 80  # RapidFuzz score threshold (0-100)

    # Chat context control
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "6"))

    # LLM generation speed tuning for Ollama (see app/services/llm.py)
    # These are only relevant when Groq is NOT being used.
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "200"))
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "2048"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "60m")

    # Translation-specific model/settings (see app/services/translator.py).
    OLLAMA_TRANSLATE_MODEL: str = os.getenv("OLLAMA_TRANSLATE_MODEL", "") or None
    OLLAMA_TRANSLATE_NUM_PREDICT: int = int(os.getenv("OLLAMA_TRANSLATE_NUM_PREDICT", "200"))

    # For general/hybrid questions in a non-English language:
    # True (default) = single LLM call in target language (fastest).
    # False = two calls (English draft then translate) — slower but sometimes more accurate.
    HYBRID_SINGLE_PASS: bool = os.getenv("HYBRID_SINGLE_PASS", "true").lower() != "false"
    OLLAMA_TIMEOUT_SECONDS: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    # ── Cloud LLM: Groq ───────────────────────────────────────────────────────
    # FREE tier at https://console.groq.com — no credit card required.
    # When GROQ_API_KEY is set, Groq is used as the PRIMARY LLM provider.
    # Responses are typically 50-200x faster than local Ollama on CPU.
    # Ollama is kept as automatic fallback if the key is absent or the API fails.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # Recommended free-tier fast models:
    #   llama-3.1-8b-instant  — fastest, best for Q&A
    #   llama3-8b-8192        — slightly slower but larger context
    #   mixtral-8x7b-32768    — strongest, good for complex legal reasoning
    #   gemma2-9b-it          — Google's model, good instruction following
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MAX_TOKENS: int = int(os.getenv("GROQ_MAX_TOKENS", "800"))

    # LLM_PROVIDER: "auto" | "groq" | "ollama"
    # "auto" (default) = use Groq if key set, else Ollama
    # "groq" = force Groq (errors if key missing)
    # "ollama" = force local Ollama
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto")

    @property
    def use_groq(self) -> bool:
        """True when Groq should be the active LLM provider."""
        if self.LLM_PROVIDER == "groq":
            return bool(self.GROQ_API_KEY)
        if self.LLM_PROVIDER == "ollama":
            return False
        # auto: use Groq if key is available
        return bool(self.GROQ_API_KEY)

    SUPPORTED_LANGUAGES: dict = {}  # populated below after class definition, from app.i18n.messages


settings = Settings()
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.DATA_DIR, exist_ok=True)

# Single source of truth for supported languages lives in app.i18n.messages
# (display name -> speech locale / langdetect code), imported here so the
# rest of the codebase can keep using `settings.SUPPORTED_LANGUAGES`.
from app.i18n.messages import LANGUAGE_LOCALES  # noqa: E402
settings.SUPPORTED_LANGUAGES = {name: info["code"] for name, info in LANGUAGE_LOCALES.items()}
