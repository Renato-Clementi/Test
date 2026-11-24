from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mosaika.models import Utente
from mosaika.routers.deps import get_current_user, get_db
from mosaika.services.assistente import rispondi

router = APIRouter(tags=["assistente"])


class DomandaIn(BaseModel):
    domanda: str


@router.post("/assistente")
def chiedi(
    body: DomandaIn,
    request: Request,
    db: Session = Depends(get_db),
    _: Utente = Depends(get_current_user),
):
    try:
        return rispondi(
            db,
            request.app.state.settings,
            request.app.state.ai_provider,
            body.domanda,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
