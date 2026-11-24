from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mosaika.models import Utente
from mosaika.routers.deps import get_current_user, get_db
from mosaika.services.obiezioni import (
    DatoNonValido,
    NonAutorizzato,
    ObiezioneNonTrovata,
    aggiorna,
    crea,
    elenco,
)

router = APIRouter(prefix="/obiezioni", tags=["obiezioni"])


class NuovaObiezione(BaseModel):
    domanda: str
    risposta: str | None = None
    validata: bool = False
    comune: str | None = None


class AggiornaObiezione(BaseModel):
    domanda: str | None = None
    risposta: str | None = None
    validata: bool | None = None
    comune: str | None = None


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NonAutorizzato):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, DatoNonValido):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ObiezioneNonTrovata):
        return HTTPException(status_code=404, detail="Obiezione non trovata.")
    raise exc


@router.get("")
def lista(
    q: str | None = None,
    db: Session = Depends(get_db),
    _: Utente = Depends(get_current_user),
):
    return {"obiezioni": elenco(db, q)}


@router.post("")
def nuova(
    body: NuovaObiezione,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return crea(db, body.model_dump(), utente)
    except (NonAutorizzato, DatoNonValido) as exc:
        raise _http(exc) from exc


@router.patch("/{obiezione_id}")
def modifica(
    obiezione_id: int,
    body: AggiornaObiezione,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return aggiorna(
            db,
            obiezione_id,
            body.model_dump(),
            set(body.model_fields_set),
            utente,
        )
    except (NonAutorizzato, DatoNonValido, ObiezioneNonTrovata) as exc:
        raise _http(exc) from exc
