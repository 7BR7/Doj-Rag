"""
POST /api/chat  (requires authentication - see app/routes/deps.py)
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import ChatRequest, ChatResponse
from app.services.chat_service import handle_chat_message
from app.database.mongodb import MongoConnectionError
from app.services.llm import OllamaUnavailableError
from app.routes.deps import get_current_user

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("doj_rag.routes.chat")


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        result = handle_chat_message(
            message=req.message,
            conversation_id=req.conversation_id,
            language=req.language,
            # The authenticated user's ID always wins - conversations belong
            # to whoever is logged in, not to a client-supplied field.
            user_id=current_user["user_id"],
        )
        return ChatResponse(**result)
    except MongoConnectionError as e:
        logger.error(str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error handling chat message")
        raise HTTPException(status_code=500, detail="Something went wrong processing your message.")
