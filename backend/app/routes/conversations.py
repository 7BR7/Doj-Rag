"""
GET /api/conversations
GET /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}
POST /api/conversations           (explicit "new conversation")
PUT /api/conversations/{conversation_id}/truncate
DELETE /api/conversations/{conversation_id}/messages
POST /api/feedback
GET/PUT /api/settings/me

All routes require authentication (see app/routes/deps.py) and are scoped to
the logged-in user - one person's conversation history is never visible to
another account.
"""
import logging
import uuid
from fastapi import APIRouter, HTTPException, Depends
from app.database.mongodb import (
    conversations_col, messages_col, feedback_col, settings_col, now, MongoConnectionError
)
from app.models.schemas import (
    ConversationSummary, ConversationDetail, MessageOut, FeedbackRequest, UserSettings
)
from app.routes.deps import get_current_user

router = APIRouter(prefix="/api", tags=["conversations"])
logger = logging.getLogger("doj_rag.routes.conversations")


def _owned_conversation_or_404(conversation_id: str, user_id: str):
    conv = conversations_col().find_one({"conversation_id": conversation_id})
    if not conv or conv.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


@router.get("/conversations")
def list_conversations(current_user: dict = Depends(get_current_user)):
    try:
        cursor = conversations_col().find({"user_id": current_user["user_id"]}).sort("updated_at", -1)
        results = []
        for conv in cursor:
            count = messages_col().count_documents({"conversation_id": conv["conversation_id"]})
            results.append(ConversationSummary(
                conversation_id=conv["conversation_id"],
                title=conv.get("title") or "New conversation",
                updated_at=conv["updated_at"].isoformat(),
                message_count=count,
            ))
        return results
    except MongoConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/conversations")
def create_conversation(current_user: dict = Depends(get_current_user)):
    new_id = str(uuid.uuid4())
    conversations_col().insert_one({
        "conversation_id": new_id,
        "user_id": current_user["user_id"],
        "title": "New conversation",
        "created_at": now(),
        "updated_at": now(),
    })
    return {"conversation_id": new_id}


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    conv = _owned_conversation_or_404(conversation_id, current_user["user_id"])

    msgs = list(messages_col().find({"conversation_id": conversation_id}).sort("created_at", 1))
    message_list = [
        MessageOut(
            sender=m["sender"],
            message=m["message"],
            language=m.get("language", "English"),
            sources=m.get("sources", []),
            created_at=m["created_at"].isoformat(),
        )
        for m in msgs
    ]
    return ConversationDetail(
        conversation_id=conversation_id,
        title=conv.get("title") or "New conversation",
        messages=message_list,
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    _owned_conversation_or_404(conversation_id, current_user["user_id"])
    conversations_col().delete_one({"conversation_id": conversation_id})
    messages_col().delete_many({"conversation_id": conversation_id})
    return {"status": "deleted", "conversation_id": conversation_id}


@router.delete("/conversations/{conversation_id}/messages")
def clear_conversation_messages(conversation_id: str, current_user: dict = Depends(get_current_user)):
    _owned_conversation_or_404(conversation_id, current_user["user_id"])
    messages_col().delete_many({"conversation_id": conversation_id})
    return {"status": "cleared", "conversation_id": conversation_id}


@router.put("/conversations/{conversation_id}/truncate")
def truncate_conversation(conversation_id: str, keep_count: int, current_user: dict = Depends(get_current_user)):
    """
    Used when the user edits a previously-sent message: deletes every message
    after position `keep_count` (0-indexed count of messages to retain, in
    chronological order) so the edited message can be resent as the new
    continuation of the conversation, instead of appending a duplicate branch.
    """
    _owned_conversation_or_404(conversation_id, current_user["user_id"])
    msgs = list(
        messages_col().find({"conversation_id": conversation_id}).sort("created_at", 1)
    )
    to_delete = msgs[keep_count:]
    if to_delete:
        ids = [m["_id"] for m in to_delete]
        messages_col().delete_many({"_id": {"$in": ids}})
    return {"status": "truncated", "kept": keep_count, "deleted": len(to_delete)}


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, current_user: dict = Depends(get_current_user)):
    feedback_col().insert_one({
        "user_id": current_user["user_id"],
        "conversation_id": req.conversation_id,
        "message_index": req.message_index,
        "rating": req.rating,
        "comment": req.comment,
        "created_at": now(),
    })
    return {"status": "recorded"}


@router.get("/settings/me", response_model=UserSettings)
def get_settings(current_user: dict = Depends(get_current_user)):
    doc = settings_col().find_one({"user_id": current_user["user_id"]})
    if not doc:
        return UserSettings()
    return UserSettings(
        preferred_language=doc.get("preferred_language", "English"),
        voice_enabled=doc.get("voice_enabled", True),
        auto_speak=doc.get("auto_speak", False),
    )


@router.put("/settings/me")
def update_settings(settings_in: UserSettings, current_user: dict = Depends(get_current_user)):
    settings_col().update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {**settings_in.model_dump(), "user_id": current_user["user_id"], "updated_at": now()}},
        upsert=True,
    )
    return {"status": "updated"}
