from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..schemas import LoginIn, RegisterIn, TokenOut
from ..security import create_token, current_user, hash_password, verify_password
from ..state import state

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/register", status_code=201, summary="Cria uma conta")
def register(body: RegisterIn):
    if not settings.allow_registration:
        raise HTTPException(403, "Cadastro desabilitado")
    if not state.db.create_user(body.username, hash_password(body.password)):
        raise HTTPException(409, "Usuário já existe")
    return {"username": body.username}


@router.post("/login", response_model=TokenOut, summary="Gera um token JWT")
def login(body: LoginIn):
    user = state.db.get_user(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Usuário ou senha inválidos")
    return TokenOut(access_token=create_token(body.username), expires_in=settings.token_expire_minutes * 60)


@router.get("/me", summary="Usuário do token atual")
def me(user: str = Depends(current_user)):
    return {"username": user}
