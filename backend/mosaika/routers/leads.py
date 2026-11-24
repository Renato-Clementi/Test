from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mosaika.models import Utente
from mosaika.routers.deps import get_current_user, get_db
from mosaika.services.leads import (
    DatoNonValido,
    LeadNonTrovato,
    aggiorna,
    elenco,
    scheda,
)
from mosaika.services.sync import sincronizza_lead
from mosaika.timeutil import adesso

router = APIRouter(prefix="/leads", tags=["leads"])


class AggiornaLeadIn(BaseModel):
    stato: str | None = None
    zona: str | None = None
    qualifica: dict | None = None
    versione: str | None = None
    sopralluogo: str | None = None
    video_il: datetime | None = None
    giro: dict | None = None
    foto_ricevute: bool | None = None
    note: str | None = None


@router.get("")
def lista(
    filtro: str = "da_lavorare",
    db: Session = Depends(get_db),
    _: Utente = Depends(get_current_user),
):
    try:
        return elenco(db, filtro)
    except DatoNonValido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/aggiorna")
def aggiorna_dalla_fonte(
    request: Request,
    db: Session = Depends(get_db),
    _: Utente = Depends(get_current_user),
):
    try:
        request.app.state.sync_count = sincronizza_lead(db, request.app.state.odoo_source)
    except Exception as exc:
        request.app.state.sync_error = str(exc)
        raise HTTPException(
            status_code=502, detail="Lettura della fonte non riuscita."
        ) from exc
    request.app.state.last_sync = adesso()
    request.app.state.sync_error = None
    return elenco(db)


@router.get("/{odoo_lead_id}")
def dettaglio(
    odoo_lead_id: int,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return scheda(db, odoo_lead_id, utente.nome)
    except LeadNonTrovato as exc:
        raise HTTPException(status_code=404, detail="Lead non trovato.") from exc


@router.patch("/{odoo_lead_id}")
def aggiorna_lead(
    odoo_lead_id: int,
    body: AggiornaLeadIn,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return aggiorna(
            db,
            odoo_lead_id,
            body.model_dump(),
            set(body.model_fields_set),
            utente,
        )
    except LeadNonTrovato as exc:
        raise HTTPException(status_code=404, detail="Lead non trovato.") from exc
    except DatoNonValido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
