import json
import shutil
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mosaika.models import Utente
from mosaika.routers.deps import get_current_user, get_db
from mosaika.sopralluogo.servizio import (
    Conflitto,
    DatoNonValido,
    NonAutorizzato,
    NonTrovato,
    aggiungi_parte,
    aggiorna_voce,
    apri_upload,
    completa_upload,
    crea_rilievo,
    dettaglio_modello,
    dettaglio_rilievo,
    export_zip,
    importa_modello,
    leggi_file,
    lista_modelli,
    lista_rilievi,
    salva_chiusura,
    salva_file,
)

router = APIRouter(prefix="/sopralluogo", tags=["sopralluogo"])


class NuovoRilievo(BaseModel):
    modello: str
    titolo: str | None = None
    sito: str | None = None
    odoo_opportunity_id: int | None = None


class MisuraIn(BaseModel):
    etichetta: str | None = None
    valore: str = ""
    unita: str = ""
    rilevata_il: str | None = None
    temperatura_esterna: str | None = None


class VoceIn(BaseModel):
    stato: str | None = None
    testo: str | None = None
    chi_invia: str | None = None
    entro_il: str | None = None
    misure: list[MisuraIn] | None = None


class UploadIn(BaseModel):
    voce_id: int
    tipo: str
    nome_originale: str
    content_type: str = "application/octet-stream"
    total_size: int
    vista_insieme: bool = False
    consenso: bool = False
    consenso_nome: str | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    gps_accuracy: float | None = None


class ChiusuraIn(BaseModel):
    tecnico_nome: str | None = None
    firmato_il: str | None = None
    firma_png: str | None = None
    chiudi: bool = False


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NonAutorizzato):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, DatoNonValido):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, NonTrovato):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, Conflitto):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def _flag(valore: str | None) -> bool:
    return str(valore or "").strip().lower() in {"1", "true", "on", "si", "sì", "yes"}


@router.get("/modelli")
def modelli(db: Session = Depends(get_db), _: Utente = Depends(get_current_user)):
    return {"modelli": lista_modelli(db)}


@router.get("/modelli/{codice}")
def modello(codice: str, db: Session = Depends(get_db), _: Utente = Depends(get_current_user)):
    try:
        return dettaglio_modello(db, codice)
    except NonTrovato as exc:
        raise _http(exc) from exc


@router.post("/modelli", status_code=201)
async def importa(
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="Modello troppo grande.")
    ctype = request.headers.get("content-type", "")
    try:
        testo = raw.decode("utf-8")
        if "yaml" in ctype or "yml" in ctype:
            dati = yaml.safe_load(testo)
        else:
            dati = json.loads(testo)
    except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Modello non leggibile.") from exc
    try:
        return importa_modello(db, dati, utente)
    except (NonAutorizzato, DatoNonValido, Conflitto) as exc:
        raise _http(exc) from exc


@router.get("/rilievi")
def rilievi(db: Session = Depends(get_db), _: Utente = Depends(get_current_user)):
    return {"rilievi": lista_rilievi(db)}


@router.post("/rilievi", status_code=201)
def nuovo(
    body: NuovoRilievo,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return crea_rilievo(db, body.model_dump(), utente)
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc


@router.get("/rilievi/{rilievo_id}")
def rilievo(rilievo_id: int, db: Session = Depends(get_db), _: Utente = Depends(get_current_user)):
    try:
        return dettaglio_rilievo(db, rilievo_id)
    except NonTrovato as exc:
        raise _http(exc) from exc


@router.put("/rilievi/{rilievo_id}/voci/{voce_id}")
def voce(
    rilievo_id: int,
    voce_id: int,
    body: VoceIn,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return aggiorna_voce(db, rilievo_id, voce_id, body.model_dump(), utente)
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc


@router.post("/rilievi/{rilievo_id}/file")
def carica_file(
    rilievo_id: int,
    request: Request,
    voce_id: int = Form(...),
    tipo: str = Form(...),
    file: UploadFile = File(...),
    vista_insieme: str = Form("false"),
    consenso: str = Form("false"),
    consenso_nome: str = Form(""),
    gps_lat: str = Form(""),
    gps_lon: str = Form(""),
    gps_accuracy: str = Form(""),
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    settings = request.app.state.settings
    with tempfile.NamedTemporaryFile(delete=False) as temporaneo:
        percorso = Path(temporaneo.name)
        shutil.copyfileobj(file.file, temporaneo)
    try:
        if percorso.stat().st_size > int(settings.upload_max_bytes):
            raise HTTPException(status_code=400, detail="File troppo grande.")
        return salva_file(
            db,
            request.app.state.storage,
            rilievo_id,
            utente,
            voce_id=voce_id,
            tipo=tipo,
            nome_originale=file.filename or "file",
            content_type=file.content_type or "application/octet-stream",
            sorgente=percorso,
            vista_insieme=_flag(vista_insieme),
            consenso=_flag(consenso),
            consenso_nome=consenso_nome,
            gps_lat=gps_lat,
            gps_lon=gps_lon,
            gps_accuracy=gps_accuracy,
        )
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc
    finally:
        percorso.unlink(missing_ok=True)


@router.post("/rilievi/{rilievo_id}/upload", status_code=201)
def apri(
    rilievo_id: int,
    body: UploadIn,
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return apri_upload(db, request.app.state.settings, rilievo_id, body.model_dump(), utente)
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc


@router.put("/rilievi/{rilievo_id}/upload/{upload_id}/parti/{indice}")
async def parte(
    rilievo_id: int,
    upload_id: str,
    indice: int,
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    settings = request.app.state.settings
    lunghezza = request.headers.get("content-length")
    if lunghezza:
        try:
            if int(lunghezza) > int(settings.upload_chunk_bytes):
                raise HTTPException(status_code=400, detail="Parte troppo grande.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Parte non valida.") from exc
    data = await request.body()
    try:
        return aggiungi_parte(db, settings, rilievo_id, upload_id, indice, data, utente)
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc


@router.post("/rilievi/{rilievo_id}/upload/{upload_id}/completa")
def completa(
    rilievo_id: int,
    upload_id: str,
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return completa_upload(
            db,
            request.app.state.storage,
            request.app.state.settings,
            rilievo_id,
            upload_id,
            utente,
        )
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc


@router.get("/rilievi/{rilievo_id}/file/{file_id}")
def scarica(
    rilievo_id: int,
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: Utente = Depends(get_current_user),
):
    try:
        percorso, riga = leggi_file(db, request.app.state.storage, rilievo_id, file_id)
    except (NonTrovato, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="File non trovato.") from exc
    return FileResponse(percorso, media_type=riga.content_type, filename=riga.nome_assegnato)


@router.get("/rilievi/{rilievo_id}/chiusura")
def chiusura(rilievo_id: int, db: Session = Depends(get_db), _: Utente = Depends(get_current_user)):
    try:
        return dettaglio_rilievo(db, rilievo_id)["chiusura"]
    except NonTrovato as exc:
        raise _http(exc) from exc


@router.put("/rilievi/{rilievo_id}/chiusura")
def aggiorna_chiusura(
    rilievo_id: int,
    body: ChiusuraIn,
    request: Request,
    db: Session = Depends(get_db),
    utente: Utente = Depends(get_current_user),
):
    try:
        return salva_chiusura(
            db,
            request.app.state.storage,
            rilievo_id,
            body.model_dump(),
            utente,
        )
    except (NonAutorizzato, DatoNonValido, NonTrovato) as exc:
        raise _http(exc) from exc


@router.get("/rilievi/{rilievo_id}/export")
def esporta(
    rilievo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: Utente = Depends(get_current_user),
):
    try:
        contenuto, nome = export_zip(db, request.app.state.storage, rilievo_id)
    except NonTrovato as exc:
        raise _http(exc) from exc
    return Response(
        content=contenuto,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
