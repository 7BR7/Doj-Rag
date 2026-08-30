"""
FastAPI dependency for extracting and validating the authenticated user from
an `Authorization: Bearer <token>` header. Any route that should be scoped to
"this particular user's" data (conversations, chat, settings) depends on
`get_current_user`.
"""
from fastapi import Header, HTTPException
from typing import Optional, Dict
from app.services.auth import decode_access_token
from app.database.mongodb import users_col


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")

    user_id = payload.get("sub")
    user = users_col().find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="Account not found. Please log in again.")

    return {"user_id": user["user_id"], "username": user["username"], "email": user.get("email")}
