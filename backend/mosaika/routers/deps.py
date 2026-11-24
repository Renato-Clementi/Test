from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from mosaika.auth import COOKIE, leggi_sessione
from mosaika.models import Utente


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def utente_pubblico(utente: Utente) -> dict:
    return {
        "id": utente.id,
        "nome": utente.nome,
        "email": utente.email,
        "ruolo": utente.ruolo,
    }


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Utente:
    token = request.cookies.get(COOKIE)
    uid = leggi_sessione(token, request.app.state.settings.session_secret)
    if not uid:
        raise HTTPException(status_code=401, detail="Accesso richiesto.")
    utente = db.get(Utente, uid)
    if utente is None:
        raise HTTPException(status_code=401, detail="Accesso richiesto.")
    return utente
