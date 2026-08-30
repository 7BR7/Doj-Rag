"""
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import UserRegister, UserLogin, TokenResponse, UserOut
from app.database.mongodb import users_col, now, MongoConnectionError
from app.services.auth import hash_password, verify_password, create_access_token, new_user_id
from app.routes.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("doj_rag.routes.auth")


@router.post("/register", response_model=TokenResponse)
def register(req: UserRegister):
    try:
        existing = users_col().find_one({"username": req.username})
    except MongoConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if existing:
        raise HTTPException(status_code=409, detail="That username is already taken.")

    if req.email:
        existing_email = users_col().find_one({"email": req.email})
        if existing_email:
            raise HTTPException(status_code=409, detail="That email is already registered.")

    user_id = new_user_id()
    users_col().insert_one({
        "user_id": user_id,
        "username": req.username,
        "email": req.email,
        "password_hash": hash_password(req.password),
        "created_at": now(),
    })

    token = create_access_token(user_id, req.username)
    return TokenResponse(
        access_token=token,
        user=UserOut(user_id=user_id, username=req.username, email=req.email),
    )


@router.post("/login", response_model=TokenResponse)
def login(req: UserLogin):
    try:
        user = users_col().find_one({"username": req.username})
    except MongoConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    token = create_access_token(user["user_id"], user["username"])
    return TokenResponse(
        access_token=token,
        user=UserOut(user_id=user["user_id"], username=user["username"], email=user.get("email")),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    return UserOut(**current_user)
