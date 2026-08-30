"""
POST /api/chat  (requires authentication - see app/routes/deps.py)

Streams the response as newline-delimited JSON (NDJSON) events rather than
a single JSON blob - see app/services/chat_service.stream_chat_message for
the event shapes. This is what lets the answer appear as it's generated
instead of the browser waiting in silence for the full response, and lets
the frontend cancel mid-generation (closing the connection stops the
generator, which stops the underlying Ollama call too).
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest
from app.services.chat_service import stream_chat_message
from app.database.mongodb import MongoConnectionError
from app.routes.deps import get_current_user

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("doj_rag.routes.chat")


@router.post("/chat")
async def chat(req: ChatRequest, request: Request, current_user: dict = Depends(get_current_user)):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    async def event_stream():
        try:
            async for event in stream_chat_message(
                message=req.message,
                conversation_id=req.conversation_id,
                language=req.language,
                user_id=current_user["user_id"],
            ):
                # If the client has already disconnected (e.g. the user
                # started editing an earlier message), stop generating
                # entirely instead of continuing to burn CPU/GPU on tokens
                # nobody will see.
                if await request.is_disconnected():
                    logger.info("Client disconnected mid-stream; stopping generation.")
                    return
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except MongoConnectionError as e:
            logger.error(str(e))
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"
        except ValueError as e:
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"
        except Exception:
            logger.exception("Unexpected error while streaming chat message")
            yield json.dumps(
                {"type": "error", "message": "Something went wrong processing your message."},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
