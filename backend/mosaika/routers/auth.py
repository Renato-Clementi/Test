from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mosaika.auth import COOKIE, firma_sessione, verify_password
from mosaika.models import Utente
from mosaika.routers.deps import get_current_user, get_db, utente_pubblico

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = body.email.strip().lower()
    utente = db.scalar(select(Utente).where(func.lower(Utente.email) == email))
    settings = request.app.state.settings
    if utente is None or not verify_password(body.password, utente.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide.")
    token = firma_sessione(utente.id, settings.session_secret, settings.session_days)
    response.set_cookie(
        key=COOKIE,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
    )
    return utente_pubblico(utente)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(utente: Utente = Depends(get_current_user)):
    return utente_pubblico(utente)
