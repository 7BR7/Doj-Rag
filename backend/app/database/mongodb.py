"""
MongoDB connection and collection accessors.
Fails gracefully with a clear error if MongoDB is not reachable, rather than
crashing the whole app on import.
"""
import logging
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError
from app.config import settings

logger = logging.getLogger("doj_rag.mongodb")

_client = None
_db = None


class MongoConnectionError(Exception):
    pass


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=4000)
    return _client


def get_db():
    global _db
    if _db is None:
        client = get_client()
        try:
            client.admin.command("ping")
        except ServerSelectionTimeoutError as e:
            raise MongoConnectionError(
                f"Could not connect to MongoDB at {settings.MONGODB_URI}. "
                "Is MongoDB running? Start it with `mongod` or via Docker."
            ) from e
        _db = client[settings.DATABASE_NAME]
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(db):
    db.conversations.create_index([("user_id", ASCENDING), ("updated_at", ASCENDING)])
    db.conversations.create_index([("conversation_id", ASCENDING)], unique=True)
    db.messages.create_index([("conversation_id", ASCENDING), ("created_at", ASCENDING)])
    db.chunks_metadata.create_index([("document_id", ASCENDING)])
    db.chunks_metadata.create_index([("article", ASCENDING)])
    db.chunks_metadata.create_index([("section", ASCENDING)])
    db.chunks_metadata.create_index([("rule", ASCENDING)])
    db.chunks_metadata.create_index([("chunk_id", ASCENDING)], unique=True)
    db.documents.create_index([("document_id", ASCENDING)], unique=True)
    db.users.create_index([("user_id", ASCENDING)], unique=True)
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.translations.create_index([("cache_key", ASCENDING)], unique=True)


def now():
    return datetime.now(timezone.utc)


# ---- Collection helpers -------------------------------------------------

def conversations_col():
    return get_db().conversations


def messages_col():
    return get_db().messages


def documents_col():
    return get_db().documents


def chunks_col():
    return get_db().chunks_metadata


def feedback_col():
    return get_db().feedback


def settings_col():
    return get_db().settings


def users_col():
    return get_db().users
