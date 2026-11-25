"""Rilievi, file e controlli di chiusura. L'id Odoo, se presente, è solo un numero."""

from __future__ import annotations

import base64
import hashlib
import math
import re
import shutil
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mosaika.auth import puo_scrivere_sopralluogo
from mosaika.config import Settings
from mosaika.models import Utente
from mosaika.sopralluogo.export import voce_etichetta
from mosaika.sopralluogo.models import (
    ContatoreFile,
    FileRilievo,
    Misura,
    ModelloChecklist,
    Rilievo,
    RispostaVoce,
    SezioneChecklist,
    UploadSessione,
    VoceChecklist,
)
from mosaika.sopralluogo.storage import Storage
from mosaika.sopralluogo.template_io import ModelloNonValido, normalizza
from mosaika.timeutil import ROMA, adesso

TIPI_FILE = {"F", "V", "A", "D"}
STATI_VOCE = {"aperto", "fatto", "non_applicabile"}
_NUMERO = re.compile(r"-?\d+(?:\.\d+)?")
_EXT = re.compile(r"^\.[a-z0-9]{1,5}$")
_ESTENSIONI = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "audio/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/aac": ".aac",
    "application/pdf": ".pdf",
}


class NonAutorizzato(PermissionError):
    pass


class DatoNonValido(ValueError):
    pass


class NonTrovato(LookupError):
    pass


class Conflitto(Exception):
    pass


def importa_modello(db: Session, dati: dict, utente: Utente) -> dict:
    _scrive(utente)
    try:
        pulito = normalizza(dati)
    except ModelloNonValido as exc:
        raise DatoNonValido(str(exc)) from exc
    if db.get(ModelloChecklist, pulito["codice"]) is not None:
        raise Conflitto("Questo modello esiste già. Per una revisione nuova usa un codice nuovo.")
    _scrivi_modello(db, pulito)
    db.commit()
    return dettaglio_modello(db, pulito["codice"])


def _scrivi_modello(db: Session, pulito: dict) -> None:
    db.add(
        ModelloChecklist(
            codice=pulito["codice"],
            titolo=pulito["titolo"],
            sito=pulito["sito"],
            revisione=pulito["revisione"],
            odoo_opportunity_id=pulito["odoo_opportunity_id"],
            perimetro=pulito["perimetro"],
            istruzioni=pulito["istruzioni"],
            importato_il=adesso(),
        )
    )
    db.flush()
    for sezione in pulito["sezioni"]:
        riga = SezioneChecklist(
            modello_codice=pulito["codice"],
            ordine=sezione["ordine"],
            codice=sezione["codice"],
            titolo=sezione["titolo"],
            sottotitolo=sezione["sottotitolo"],
            prefisso=sezione["prefisso"],
            tipo=sezione["tipo"],
        )
        db.add(riga)
        db.flush()
        for voce in sezione["voci"]:
            db.add(
                VoceChecklist(
                    sezione_id=riga.id,
                    ordine=voce["ordine"],
                    testo=voce["testo"],
                    evidenze=voce["evidenze"],
                    capitolo=voce["capitolo"],
                    unita_suggerita=voce["unita_suggerita"],
                    misure_minime=voce["misure_minime"],
                    temperatura=voce["temperatura"],
                    con_ora=voce["con_ora"],
                    consenso_richiesto=voce["consenso_richiesto"],
                    chiave=voce["chiave"],
                    ripetibile=voce["ripetibile"],
                    etichette=voce["etichette"],
                )
            )
    db.flush()


def lista_modelli(db: Session) -> list[dict]:
    righe = db.scalars(select(ModelloChecklist).order_by(ModelloChecklist.codice)).all()
    return [_modello_breve(riga) for riga in righe]


def dettaglio_modello(db: Session, codice: str) -> dict:
    modello = db.get(ModelloChecklist, codice)
    if modello is None:
        raise NonTrovato("Modello non trovato.")
    sezioni = _sezioni(db, modello.codice)
    voci = _voci_di(db, [s.id for s in sezioni])
    return {
        **_modello_breve(modello),
        "istruzioni": modello.istruzioni or "",
        "sezioni": [
            {
                **_sezione_breve(sezione),
                "voci": [_voce_modello(voce) for voce in voci.get(sezione.id, [])],
            }
            for sezione in sezioni
        ],
    }


def lista_rilievi(db: Session) -> list[dict]:
    righe = db.scalars(select(Rilievo).order_by(Rilievo.creato_il.desc())).all()
    return [_rilievo_breve(db, riga) for riga in righe]


def crea_rilievo(db: Session, dati: dict, utente: Utente) -> dict:
    _scrive(utente)
    codice = (dati.get("modello") or "").strip()
    modello = db.get(ModelloChecklist, codice)
    if modello is None:
        raise NonTrovato("Modello non trovato.")
    titolo = (dati.get("titolo") or modello.titolo or "").strip()
    sito = (dati.get("sito") or modello.sito or "").strip()
    if not sito:
        raise DatoNonValido("Indica il sito del sopralluogo.")
    if len(titolo) > 200 or len(sito) > 200:
        raise DatoNonValido("Titolo o sito troppo lunghi.")
    opportunita = dati.get("odoo_opportunity_id")
    if opportunita in ("", None):
        opportunita = modello.odoo_opportunity_id
    else:
        try:
            opportunita = int(opportunita)
        except (TypeError, ValueError) as exc:
            raise DatoNonValido("L'id opportunità deve essere un numero.") from exc
        if opportunita <= 0:
            raise DatoNonValido("L'id opportunità deve essere positivo.")
    rilievo = Rilievo(
        modello_codice=modello.codice,
        titolo=titolo,
        sito=sito,
        odoo_opportunity_id=opportunita,
        stato="aperto",
        creato_il=adesso(),
        creato_da=utente.id,
        tecnico_nome=utente.nome,
    )
    db.add(rilievo)
    db.commit()
    return dettaglio_rilievo(db, rilievo.id)


def dettaglio_rilievo(db: Session, rilievo_id: int) -> dict:
    return _pubblico(_albero(db, _rilievo(db, rilievo_id)))


def aggiorna_voce(db: Session, rilievo_id: int, voce_id: int, dati: dict, utente: Utente) -> dict:
    _scrive(utente)
    rilievo = _rilievo(db, rilievo_id)
    voce = _voce_del_rilievo(db, rilievo, voce_id)
    risposta = _risposta(db, rilievo, voce, utente)
    if "stato" in dati and dati["stato"] is not None:
        stato = str(dati["stato"]).strip()
        if stato not in STATI_VOCE:
            raise DatoNonValido("Stato voce non valido.")
        risposta.stato = stato
    if "testo" in dati and dati["testo"] is not None:
        testo = str(dati["testo"]).strip()
        if len(testo) > 4000:
            raise DatoNonValido("Nota troppo lunga.")
        risposta.testo = testo or None
    if "chi_invia" in dati and dati["chi_invia"] is not None:
        chi = str(dati["chi_invia"]).strip()
        if len(chi) > 160:
            raise DatoNonValido("Il nome di chi invia è troppo lungo.")
        risposta.chi_invia = chi or None
    if "entro_il" in dati:
        risposta.entro_il = _data(dati.get("entro_il"))
    if dati.get("misure") is not None:
        if not isinstance(dati["misure"], list):
            raise DatoNonValido("Le misure devono essere un elenco.")
        _sostituisci_misure(db, risposta, voce, dati["misure"])
    risposta.aggiornato_il = adesso()
    risposta.aggiornato_da = utente.id
    db.commit()
    return dettaglio_rilievo(db, rilievo.id)


def salva_file(
    db: Session,
    storage: Storage,
    rilievo_id: int,
    utente: Utente,
    *,
    voce_id: int,
    tipo: str,
    nome_originale: str,
    content_type: str,
    sorgente: Path,
    vista_insieme: bool,
    consenso: bool,
    consenso_nome: str | None,
    gps_lat,
    gps_lon,
    gps_accuracy,
) -> dict:
    _scrive(utente)
    rilievo = _rilievo(db, rilievo_id)
    voce, sezione = _voce_e_sezione(db, rilievo, voce_id)
    meta = _meta_file(
        voce,
        tipo=tipo,
        vista_insieme=vista_insieme,
        consenso=consenso,
        consenso_nome=consenso_nome,
        gps=(gps_lat, gps_lon, gps_accuracy),
    )
    _registra_file(
        db,
        storage,
        rilievo,
        voce,
        sezione,
        utente,
        sorgente=sorgente,
        nome_originale=nome_originale,
        content_type=content_type,
        meta=meta,
        nome_assegnato=None,
    )
    db.commit()
    return dettaglio_rilievo(db, rilievo.id)


def apri_upload(
    db: Session,
    settings: Settings,
    rilievo_id: int,
    dati: dict,
    utente: Utente,
) -> dict:
    _scrive(utente)
    rilievo = _rilievo(db, rilievo_id)
    try:
        totale = int(dati.get("total_size"))
    except (TypeError, ValueError) as exc:
        raise DatoNonValido("Dimensione del file non valida.") from exc
    massimo = int(settings.upload_max_bytes)
    if totale < 1 or totale > massimo:
        raise DatoNonValido("Dimensione del file non valida.")
    voce, sezione = _voce_e_sezione(db, rilievo, int(dati.get("voce_id")))
    meta = _meta_file(
        voce,
        tipo=str(dati.get("tipo") or ""),
        vista_insieme=bool(dati.get("vista_insieme")),
        consenso=bool(dati.get("consenso")),
        consenso_nome=dati.get("consenso_nome"),
        gps=(dati.get("gps_lat"), dati.get("gps_lon"), dati.get("gps_accuracy")),
    )
    chunk = max(1, int(settings.upload_chunk_bytes))
    nome = _prossimo_nome(
        db,
        rilievo.id,
        sezione.prefisso or sezione.codice,
        estensione(str(dati.get("nome_originale") or ""), str(dati.get("content_type") or "")),
    )
    sessione = UploadSessione(
        id=str(uuid.uuid4()),
        rilievo_id=rilievo.id,
        voce_id=voce.id,
        tipo=meta["tipo"],
        nome_originale=_nome_originale(str(dati.get("nome_originale") or "file")),
        nome_assegnato=nome,
        content_type=(str(dati.get("content_type") or "application/octet-stream").split(";")[0].strip() or "application/octet-stream")[:120],
        total_size=totale,
        chunk_size=chunk,
        parti_ricevute=[],
        gps_lat=meta["gps_lat"],
        gps_lon=meta["gps_lon"],
        gps_accuracy=meta["gps_accuracy"],
        vista_insieme=meta["vista_insieme"],
        consenso=meta["consenso"],
        consenso_nome=meta["consenso_nome"],
        autore_id=utente.id,
        autore_nome=utente.nome,
        creata_il=adesso(),
        completa=False,
    )
    db.add(sessione)
    db.commit()
    return {
        "id": sessione.id,
        "chunk_size": chunk,
        "nome_assegnato": nome,
        "parti": _quante_parti(totale, chunk),
        "total_size": totale,
    }


def aggiungi_parte(
    db: Session,
    settings: Settings,
    rilievo_id: int,
    upload_id: str,
    indice: int,
    data: bytes,
    utente: Utente,
) -> dict:
    _scrive(utente)
    sessione = _sessione(db, rilievo_id, upload_id)
    if sessione.completa:
        raise DatoNonValido("Upload già completato.")
    if indice < 0:
        raise DatoNonValido("Parte non valida.")
    quante = _quante_parti(sessione.total_size, sessione.chunk_size)
    if indice >= quante:
        raise DatoNonValido("Parte fuori scala.")
    attesa = _dimensione_parte(sessione.total_size, sessione.chunk_size, indice, quante)
    if len(data) != attesa:
        raise DatoNonValido("Parte di dimensione inattesa.")
    percorso = _percorso_parte(settings, sessione.id, indice)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_bytes(data)
    ricevute = sorted(set(sessione.parti_ricevute or []) | {indice})
    sessione.parti_ricevute = ricevute
    db.commit()
    return {"ricevute": ricevute, "parti": quante, "nome_assegnato": sessione.nome_assegnato}


def completa_upload(
    db: Session,
    storage: Storage,
    settings: Settings,
    rilievo_id: int,
    upload_id: str,
    utente: Utente,
) -> dict:
    _scrive(utente)
    sessione = _sessione(db, rilievo_id, upload_id)
    if sessione.completa and sessione.file_id:
        return dettaglio_rilievo(db, rilievo_id)
    quante = _quante_parti(sessione.total_size, sessione.chunk_size)
    for indice in range(quante):
        if not _percorso_parte(settings, sessione.id, indice).is_file():
            raise DatoNonValido(f"Manca la parte {indice}.")
    rilievo = _rilievo(db, rilievo_id)
    voce, sezione = _voce_e_sezione(db, rilievo, sessione.voce_id)
    with tempfile.NamedTemporaryFile(delete=False) as temporaneo:
        destinazione = Path(temporaneo.name)
    try:
        with destinazione.open("wb") as uscita:
            for indice in range(quante):
                parte = _percorso_parte(settings, sessione.id, indice)
                attesa = _dimensione_parte(sessione.total_size, sessione.chunk_size, indice, quante)
                if parte.stat().st_size != attesa:
                    raise DatoNonValido("Parte di dimensione inattesa.")
                with parte.open("rb") as ingresso:
                    shutil.copyfileobj(ingresso, uscita)
        _registra_file(
            db,
            storage,
            rilievo,
            voce,
            sezione,
            utente,
            sorgente=destinazione,
            nome_originale=sessione.nome_originale,
            content_type=sessione.content_type,
            meta={
                "tipo": sessione.tipo,
                "vista_insieme": sessione.vista_insieme,
                "consenso": sessione.consenso,
                "consenso_nome": sessione.consenso_nome,
                "gps_lat": sessione.gps_lat,
                "gps_lon": sessione.gps_lon,
                "gps_accuracy": sessione.gps_accuracy,
            },
            nome_assegnato=sessione.nome_assegnato,
            autore_nome=sessione.autore_nome,
            autore_id=sessione.autore_id,
        )
        sessione.completa = True
        sessione.file_id = db.scalars(
            select(FileRilievo.id)
            .where(FileRilievo.rilievo_id == rilievo.id, FileRilievo.nome_assegnato == sessione.nome_assegnato)
            .order_by(FileRilievo.id.desc())
        ).first()
        db.commit()
    finally:
        destinazione.unlink(missing_ok=True)
    cartella = _percorso_parte(settings, sessione.id, 0).parent
    if cartella.is_dir():
        shutil.rmtree(cartella, ignore_errors=True)
    return dettaglio_rilievo(db, rilievo.id)


def leggi_file(db: Session, storage: Storage, rilievo_id: int, file_id: int) -> tuple[Path, FileRilievo]:
    riga = db.get(FileRilievo, file_id)
    if riga is None or riga.rilievo_id != rilievo_id:
        raise NonTrovato("File non trovato.")
    return storage.open_path(riga.storage_key), riga


def salva_chiusura(
    db: Session,
    storage: Storage,
    rilievo_id: int,
    dati: dict,
    utente: Utente,
) -> dict:
    _scrive(utente)
    rilievo = _rilievo(db, rilievo_id)
    if dati.get("tecnico_nome") is not None:
        nome = str(dati.get("tecnico_nome") or "").strip()
        if len(nome) > 120:
            raise DatoNonValido("Nome del tecnico troppo lungo.")
        if nome:
            rilievo.tecnico_nome = nome
    if dati.get("firmato_il"):
        rilievo.firmato_il = _istante(dati.get("firmato_il"))
    firma = dati.get("firma_png")
    if firma:
        raw = _png(firma)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temporaneo:
            percorso = Path(temporaneo.name)
            temporaneo.write(raw)
        try:
            chiave = f"rilievi/{rilievo.id}/chiusura/firma.png"
            storage.put_file(chiave, percorso, "image/png")
            rilievo.firma_key = chiave
            if rilievo.firmato_il is None:
                rilievo.firmato_il = adesso()
        finally:
            percorso.unlink(missing_ok=True)
    if dati.get("chiudi"):
        if not (rilievo.tecnico_nome or "").strip():
            raise DatoNonValido("Indica il nome del tecnico per chiudere.")
        if not rilievo.firma_key:
            raise DatoNonValido("Serve la firma del tecnico per chiudere.")
        rilievo.stato = "chiuso"
        rilievo.chiuso_il = rilievo.firmato_il or adesso()
    db.commit()
    return dettaglio_rilievo(db, rilievo.id)


def export_zip(db: Session, storage: Storage, rilievo_id: int) -> tuple[bytes, str]:
    from mosaika.sopralluogo.export import costruisci_zip, nome_zip

    albero = _albero(db, _rilievo(db, rilievo_id))
    return costruisci_zip(albero, storage), nome_zip(albero)


def _scrive(utente: Utente) -> None:
    if not puo_scrivere_sopralluogo(utente.ruolo):
        raise NonAutorizzato("Solo tecnico e admin possono modificare un sopralluogo.")


def _rilievo(db: Session, rilievo_id: int) -> Rilievo:
    rilievo = db.get(Rilievo, rilievo_id)
    if rilievo is None:
        raise NonTrovato("Sopralluogo non trovato.")
    return rilievo


def _sessione(db: Session, rilievo_id: int, upload_id: str) -> UploadSessione:
    sessione = db.get(UploadSessione, upload_id)
    if sessione is None or sessione.rilievo_id != rilievo_id:
        raise NonTrovato("Upload non trovato.")
    return sessione


def _sezioni(db: Session, codice: str) -> list[SezioneChecklist]:
    return list(
        db.scalars(
            select(SezioneChecklist)
            .where(SezioneChecklist.modello_codice == codice)
            .order_by(SezioneChecklist.ordine)
        ).all()
    )


def _voci_di(db: Session, sezione_ids: list[int]) -> dict[int, list[VoceChecklist]]:
    if not sezione_ids:
        return {}
    righe = db.scalars(
        select(VoceChecklist)
        .where(VoceChecklist.sezione_id.in_(sezione_ids))
        .order_by(VoceChecklist.ordine)
    ).all()
    gruppi: dict[int, list[VoceChecklist]] = {}
    for riga in righe:
        gruppi.setdefault(riga.sezione_id, []).append(riga)
    return gruppi


def _voce_del_rilievo(db: Session, rilievo: Rilievo, voce_id: int) -> VoceChecklist:
    voce, _sezione = _voce_e_sezione(db, rilievo, voce_id)
    return voce


def _voce_e_sezione(db: Session, rilievo: Rilievo, voce_id: int) -> tuple[VoceChecklist, SezioneChecklist]:
    voce = db.get(VoceChecklist, voce_id)
    if voce is None:
        raise NonTrovato("Voce non trovata.")
    sezione = db.get(SezioneChecklist, voce.sezione_id)
    if sezione is None or sezione.modello_codice != rilievo.modello_codice:
        raise NonTrovato("Voce non trovata.")
    return voce, sezione


def _risposta(db: Session, rilievo: Rilievo, voce: VoceChecklist, utente: Utente) -> RispostaVoce:
    riga = db.scalar(
        select(RispostaVoce).where(
            RispostaVoce.rilievo_id == rilievo.id,
            RispostaVoce.voce_id == voce.id,
        )
    )
    if riga is None:
        riga = RispostaVoce(
            rilievo_id=rilievo.id,
            voce_id=voce.id,
            stato="aperto",
            aggiornato_il=adesso(),
            aggiornato_da=utente.id,
        )
        db.add(riga)
        db.flush()
    return riga


def _sostituisci_misure(db: Session, risposta: RispostaVoce, voce: VoceChecklist, misure: list) -> None:
    esistenti = db.scalars(select(Misura).where(Misura.risposta_id == risposta.id)).all()
    for riga in esistenti:
        db.delete(riga)
    db.flush()
    ordine = 0
    for grezza in misure:
        if not isinstance(grezza, dict):
            raise DatoNonValido("Misura non valida.")
        valore = str(grezza.get("valore") or "").strip()
        unita = str(grezza.get("unita") or "").strip()
        if not valore and not unita:
            continue
        valore = _numero(valore, "Il valore della misura deve essere un numero.")
        if not unita or len(unita) > 16:
            raise DatoNonValido("Indica l'unità della misura.")
        etichetta = str(grezza.get("etichetta") or "").strip()
        if len(etichetta) > 80:
            raise DatoNonValido("Etichetta della misura troppo lunga.")
        esterna = str(grezza.get("temperatura_esterna") or "").strip()
        if esterna:
            esterna = _numero(esterna, "La temperatura esterna deve essere un numero.")
        db.add(
            Misura(
                risposta_id=risposta.id,
                ordine=ordine,
                etichetta=etichetta or None,
                valore=valore,
                unita=unita,
                rilevata_il=_istante(grezza.get("rilevata_il")),
                temperatura_esterna=esterna or None,
            )
        )
        ordine += 1


def _meta_file(voce: VoceChecklist, *, tipo, vista_insieme, consenso, consenso_nome, gps) -> dict:
    codice = str(tipo or "").strip().upper()
    if codice not in TIPI_FILE:
        raise DatoNonValido("Tipo di file non valido.")
    if codice not in (voce.evidenze or []):
        raise DatoNonValido("Questa voce non prevede quel tipo di file.")
    consenso_valore = None
    nome = (str(consenso_nome).strip() if consenso_nome else "") or None
    if codice == "A":
        if voce.consenso_richiesto and not consenso:
            raise DatoNonValido("Per questa intervista serve il consenso di chi parla.")
        if consenso or voce.consenso_richiesto:
            consenso_valore = bool(consenso)
    lat, lon, accuracy = _gps(*gps)
    return {
        "tipo": codice,
        "vista_insieme": bool(vista_insieme) and codice == "F",
        "consenso": consenso_valore,
        "consenso_nome": nome if consenso_valore else None,
        "gps_lat": lat,
        "gps_lon": lon,
        "gps_accuracy": accuracy,
    }


def _registra_file(
    db,
    storage: Storage,
    rilievo: Rilievo,
    voce: VoceChecklist,
    sezione: SezioneChecklist,
    utente: Utente,
    *,
    sorgente: Path,
    nome_originale: str,
    content_type: str,
    meta: dict,
    nome_assegnato: str | None,
    autore_nome: str | None = None,
    autore_id: int | None = None,
) -> FileRilievo:
    dimensione = sorgente.stat().st_size
    if dimensione < 1:
        raise DatoNonValido("Il file è vuoto.")
    tipo_mime = (content_type or "application/octet-stream").split(";")[0].strip()[:120] or "application/octet-stream"
    originale = _nome_originale(nome_originale)
    if nome_assegnato:
        assegnato = nome_assegnato
    else:
        assegnato = _prossimo_nome(
            db,
            rilievo.id,
            sezione.prefisso or sezione.codice,
            estensione(originale, tipo_mime),
        )
    digest = hashlib.sha256()
    with sorgente.open("rb") as ingresso:
        for blocco in iter(lambda: ingresso.read(1024 * 1024), b""):
            digest.update(blocco)
    chiave = f"rilievi/{rilievo.id}/{sezione.prefisso or sezione.codice}/{assegnato}"
    storage.put_file(chiave, sorgente, tipo_mime)
    quando = adesso()
    riga = FileRilievo(
        rilievo_id=rilievo.id,
        voce_id=voce.id,
        tipo=meta["tipo"],
        nome_assegnato=assegnato,
        nome_originale=originale,
        content_type=tipo_mime,
        byte_size=dimensione,
        sha256=digest.hexdigest(),
        storage_key=chiave,
        creato_il=quando,
        autore_id=autore_id if autore_id is not None else utente.id,
        autore_nome=autore_nome or utente.nome,
        gps_lat=meta["gps_lat"],
        gps_lon=meta["gps_lon"],
        gps_accuracy=meta["gps_accuracy"],
        vista_insieme=meta["vista_insieme"],
        consenso=meta["consenso"],
        consenso_nome=meta["consenso_nome"],
        consenso_il=quando if meta["consenso"] else None,
    )
    db.add(riga)
    db.flush()
    return riga


def _prossimo_nome(db: Session, rilievo_id: int, prefisso: str, ext: str) -> str:
    for _ in range(3):
        try:
            with db.begin_nested():
                riga = db.scalar(
                    select(ContatoreFile)
                    .where(ContatoreFile.rilievo_id == rilievo_id, ContatoreFile.prefisso == prefisso)
                    .with_for_update()
                )
                if riga is None:
                    riga = ContatoreFile(rilievo_id=rilievo_id, prefisso=prefisso, ultimo=1)
                    db.add(riga)
                    numero = 1
                else:
                    riga.ultimo += 1
                    numero = riga.ultimo
                db.flush()
            return f"{prefisso}-{numero:02d}{ext}"
        except IntegrityError:
            continue
    raise DatoNonValido("Numero file non assegnato.")


def estensione(nome: str, content_type: str) -> str:
    suffisso = Path(nome or "").suffix.lower()
    if _EXT.match(suffisso) and suffisso not in {".exe", ".js", ".html", ".htm", ".svg"}:
        return suffisso
    return _ESTENSIONI.get((content_type or "").split(";")[0].strip().lower(), ".bin")


def _nome_originale(nome: str) -> str:
    pulito = Path(nome or "file").name.replace("\x00", "").strip() or "file"
    return pulito[:255]


def _gps(lat, lon, accuracy):
    if lat in (None, "") and lon in (None, ""):
        return None, None, None
    if lat in (None, "") or lon in (None, ""):
        raise DatoNonValido("Coordinate incomplete.")
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError) as exc:
        raise DatoNonValido("Coordinate non valide.") from exc
    if not -90 <= lat_f <= 90 or not -180 <= lon_f <= 180:
        raise DatoNonValido("Coordinate non valide.")
    precisione = None
    if accuracy not in (None, ""):
        try:
            precisione = float(accuracy)
        except (TypeError, ValueError) as exc:
            raise DatoNonValido("Precisione GPS non valida.") from exc
        if precisione < 0:
            raise DatoNonValido("Precisione GPS non valida.")
    return lat_f, lon_f, precisione


def _numero(valore: str, messaggio: str) -> str:
    testo = (valore or "").strip().replace(",", ".")
    if not _NUMERO.fullmatch(testo):
        raise DatoNonValido(messaggio)
    return testo


def _data(valore) -> date | None:
    if valore in (None, ""):
        return None
    try:
        return date.fromisoformat(str(valore)[:10])
    except ValueError as exc:
        raise DatoNonValido("Data non valida.") from exc


def _istante(valore) -> datetime | None:
    if valore in (None, ""):
        return None
    testo = str(valore).strip()
    if testo.endswith("Z"):
        testo = testo[:-1] + "+00:00"
    try:
        momento = datetime.fromisoformat(testo)
    except ValueError as exc:
        raise DatoNonValido("Data e ora non valide.") from exc
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=ROMA)
    return momento.astimezone(timezone.utc)


def _png(valore: str) -> bytes:
    dati = str(valore).strip()
    if dati.startswith("data:"):
        if "," not in dati:
            raise DatoNonValido("La firma deve essere un PNG.")
        dati = dati.split(",", 1)[1]
    try:
        raw = base64.b64decode(dati, validate=True)
    except (ValueError, TypeError) as exc:
        raise DatoNonValido("La firma deve essere un PNG.") from exc
    if len(raw) > 500_000 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DatoNonValido("La firma deve essere un PNG.")
    return raw


def _quante_parti(totale: int, chunk: int) -> int:
    return max(1, math.ceil(int(totale) / int(chunk)))


def _dimensione_parte(totale: int, chunk: int, indice: int, quante: int) -> int:
    if indice < quante - 1:
        return int(chunk)
    return int(totale) - int(chunk) * (quante - 1)


def _percorso_parte(settings: Settings, upload_id: str, indice: int) -> Path:
    return settings.storage_dir() / "parziali" / upload_id / f"{indice}.part"


def _albero(db: Session, rilievo: Rilievo) -> dict:
    modello = db.get(ModelloChecklist, rilievo.modello_codice)
    sezioni = _sezioni(db, rilievo.modello_codice)
    voci = _voci_di(db, [s.id for s in sezioni])
    risposte = {
        riga.voce_id: riga
        for riga in db.scalars(select(RispostaVoce).where(RispostaVoce.rilievo_id == rilievo.id)).all()
    }
    ids_risposta = [riga.id for riga in risposte.values()]
    misure: dict[int, list[Misura]] = {}
    if ids_risposta:
        for riga in db.scalars(
            select(Misura).where(Misura.risposta_id.in_(ids_risposta)).order_by(Misura.ordine)
        ).all():
            misure.setdefault(riga.risposta_id, []).append(riga)
    file_per_voce: dict[int, list[FileRilievo]] = {}
    for riga in db.scalars(
        select(FileRilievo).where(FileRilievo.rilievo_id == rilievo.id).order_by(FileRilievo.id)
    ).all():
        file_per_voce.setdefault(riga.voce_id, []).append(riga)
    creatore = db.get(Utente, rilievo.creato_da) if rilievo.creato_da else None
    sezioni_out = []
    for sezione in sezioni:
        voci_out = []
        for voce in voci.get(sezione.id, []):
            risposta = risposte.get(voce.id)
            file_voce = file_per_voce.get(voce.id, [])
            misure_voce = misure.get(risposta.id, []) if risposta else []
            stato = risposta.stato if risposta else "aperto"
            mancanti = _mancanti(voce, risposta, file_voce, misure_voce)
            voci_out.append(
                {
                    "id": voce.id,
                    "ordine": voce.ordine,
                    "testo": voce.testo,
                    "evidenze": list(voce.evidenze or []),
                    "capitolo": voce.capitolo,
                    "capitolo_etichetta": voce_etichetta(voce.capitolo),
                    "unita_suggerita": voce.unita_suggerita,
                    "misure_minime": voce.misure_minime,
                    "temperatura": voce.temperatura,
                    "con_ora": voce.con_ora,
                    "consenso_richiesto": voce.consenso_richiesto,
                    "chiave": voce.chiave,
                    "ripetibile": voce.ripetibile,
                    "etichette": list(voce.etichette or []),
                    "stato": stato,
                    "testo_nota": (risposta.testo if risposta and risposta.testo else ""),
                    "chi_invia": (risposta.chi_invia if risposta and risposta.chi_invia else ""),
                    "entro_il": risposta.entro_il.isoformat() if risposta and risposta.entro_il else None,
                    "mancanti": mancanti,
                    "misure": [_misura_json(riga) for riga in misure_voce],
                    "file": [_file_json(riga) for riga in file_voce],
                }
            )
        sezioni_out.append({**_sezione_breve(sezione), "voci": voci_out})
    dati = {
        "id": rilievo.id,
        "titolo": rilievo.titolo,
        "sito": rilievo.sito,
        "odoo_opportunity_id": rilievo.odoo_opportunity_id,
        "stato": rilievo.stato,
        "modello": rilievo.modello_codice,
        "modello_titolo": modello.titolo if modello else rilievo.modello_codice,
        "revisione": modello.revisione if modello else "",
        "perimetro": (modello.perimetro if modello and modello.perimetro else ""),
        "istruzioni": (modello.istruzioni if modello and modello.istruzioni else ""),
        "creato_il": rilievo.creato_il.isoformat(),
        "creato_da": creatore.nome if creatore else "",
        "tecnico_nome": rilievo.tecnico_nome or "",
        "firmato_il": rilievo.firmato_il.isoformat() if rilievo.firmato_il else None,
        "chiuso_il": rilievo.chiuso_il.isoformat() if rilievo.chiuso_il else None,
        "firma": bool(rilievo.firma_key),
        "firma_key": rilievo.firma_key,
        "sezioni": sezioni_out,
    }
    dati["chiusura"] = _chiusura(dati)
    return dati


def _pubblico(dati: dict) -> dict:
    copia = {
        chiave: valore
        for chiave, valore in dati.items()
        if chiave != "firma_key"
    }
    sezioni = []
    for sezione in dati["sezioni"]:
        voci = []
        for voce in sezione["voci"]:
            file = [{k: v for k, v in file.items() if k != "storage_key"} for file in voce["file"]]
            voci.append({**voce, "file": file})
        sezioni.append({**sezione, "voci": voci})
    copia["sezioni"] = sezioni
    return copia


def _mancanti(voce: VoceChecklist, risposta: RispostaVoce | None, file: list[FileRilievo], misure: list[Misura]) -> list[str]:
    if risposta is not None and risposta.stato == "non_applicabile":
        return []
    tipi = {riga.tipo for riga in file}
    audio_ok = any(riga.tipo == "A" and (not voce.consenso_richiesto or riga.consenso) for riga in file)
    mancanti = []
    for evidenza in voce.evidenze or []:
        if evidenza == "F" and "F" not in tipi:
            mancanti.append("F")
        elif evidenza == "V" and "V" not in tipi:
            mancanti.append("V")
        elif evidenza == "D" and "D" not in tipi:
            mancanti.append("D")
        elif evidenza == "A":
            if audio_ok:
                continue
            if "V" in tipi and not voce.consenso_richiesto:
                continue
            mancanti.append("A")
        elif evidenza == "T" and not (risposta and (risposta.testo or "").strip()):
            mancanti.append("T")
        elif evidenza == "M" and len(_misure_valide(voce, misure)) < (voce.misure_minime or 1):
            mancanti.append("M")
    return mancanti


def _misure_valide(voce: VoceChecklist, misure: list[Misura]) -> list[Misura]:
    valide = []
    for misura in misure:
        if not misura.valore or not misura.unita:
            continue
        if voce.temperatura and (misura.rilevata_il is None or not misura.temperatura_esterna):
            continue
        if voce.con_ora and misura.rilevata_il is None:
            continue
        valide.append(misura)
    return valide


def _chiusura(dati: dict) -> dict:
    senza_foto = []
    senza_misure = []
    temperature = False
    posizione = False
    documenti = []
    for sezione in dati["sezioni"]:
        if sezione["tipo"] == "raccolta":
            insieme = any(
                file["vista_insieme"] and file["tipo"] == "F"
                for voce in sezione["voci"]
                for file in voce["file"]
            )
            if not insieme:
                senza_foto.append({"codice": sezione["codice"], "titolo": sezione["titolo"]})
            voci_misura = [
                voce["testo"]
                for voce in sezione["voci"]
                if "M" in voce["mancanti"] and voce["stato"] != "non_applicabile"
            ]
            if voci_misura:
                senza_misure.append(
                    {"codice": sezione["codice"], "titolo": sezione["titolo"], "voci": voci_misura}
                )
        if sezione["tipo"] == "documenti":
            for voce in sezione["voci"]:
                if voce["stato"] in ("fatto", "non_applicabile"):
                    continue
                if any(file["tipo"] == "D" for file in voce["file"]):
                    continue
                documenti.append(
                    {
                        "voce_id": voce["id"],
                        "testo": voce["testo"],
                        "capitolo": voce["capitolo"],
                        "capitolo_etichetta": voce["capitolo_etichetta"],
                        "chi_invia": voce["chi_invia"],
                        "entro_il": voce["entro_il"],
                    }
                )
        for voce in sezione["voci"]:
            if voce.get("chiave") == "temperatura_mandata_ritorno":
                temperature = _lettura(voce, "mandata") and _lettura(voce, "ritorno")
            if voce.get("chiave") == "posizione_unita_esterna":
                posizione = voce["stato"] == "non_applicabile" or any(
                    file["tipo"] == "F" for file in voce["file"]
                )
    return {
        "senza_foto_insieme": senza_foto,
        "senza_misure": senza_misure,
        "temperature_complete": temperature,
        "posizione_fotografata": posizione,
        "documenti_mancanti": documenti,
        "tecnico_nome": dati.get("tecnico_nome") or "",
        "firmato_il": dati.get("firmato_il"),
        "chiuso_il": dati.get("chiuso_il"),
        "firma": bool(dati.get("firma")),
    }


def _lettura(voce: dict, nome: str) -> bool:
    for misura in voce["misure"]:
        etichetta = (misura.get("etichetta") or "").lower()
        if nome in etichetta and misura.get("valore") and misura.get("unita"):
            if misura.get("rilevata_il") and misura.get("temperatura_esterna"):
                return True
    return False


def _misura_json(riga: Misura) -> dict:
    return {
        "etichetta": riga.etichetta or "",
        "valore": riga.valore,
        "unita": riga.unita,
        "rilevata_il": riga.rilevata_il.isoformat() if riga.rilevata_il else None,
        "temperatura_esterna": riga.temperatura_esterna,
    }


def _file_json(riga: FileRilievo) -> dict:
    gps = None
    if riga.gps_lat is not None and riga.gps_lon is not None:
        gps = {"lat": riga.gps_lat, "lon": riga.gps_lon, "accuracy": riga.gps_accuracy}
    return {
        "id": riga.id,
        "tipo": riga.tipo,
        "nome_assegnato": riga.nome_assegnato,
        "nome_originale": riga.nome_originale,
        "content_type": riga.content_type,
        "byte_size": riga.byte_size,
        "sha256": riga.sha256,
        "storage_key": riga.storage_key,
        "creato_il": riga.creato_il.isoformat(),
        "autore": riga.autore_nome,
        "gps": gps,
        "vista_insieme": riga.vista_insieme,
        "consenso": riga.consenso,
        "consenso_nome": riga.consenso_nome,
    }


def _modello_breve(riga: ModelloChecklist) -> dict:
    return {
        "codice": riga.codice,
        "titolo": riga.titolo,
        "sito": riga.sito,
        "revisione": riga.revisione,
        "odoo_opportunity_id": riga.odoo_opportunity_id,
        "perimetro": riga.perimetro or "",
    }


def _sezione_breve(riga: SezioneChecklist) -> dict:
    return {
        "id": riga.id,
        "codice": riga.codice,
        "titolo": riga.titolo,
        "sottotitolo": riga.sottotitolo or "",
        "prefisso": riga.prefisso,
        "tipo": riga.tipo,
        "ordine": riga.ordine,
    }


def _voce_modello(voce: VoceChecklist) -> dict:
    return {
        "id": voce.id,
        "ordine": voce.ordine,
        "testo": voce.testo,
        "evidenze": list(voce.evidenze or []),
        "capitolo": voce.capitolo,
        "capitolo_etichetta": voce_etichetta(voce.capitolo),
        "unita_suggerita": voce.unita_suggerita,
        "misure_minime": voce.misure_minime,
        "temperatura": voce.temperatura,
        "con_ora": voce.con_ora,
        "consenso_richiesto": voce.consenso_richiesto,
        "chiave": voce.chiave,
        "ripetibile": voce.ripetibile,
        "etichette": list(voce.etichette or []),
    }


def _rilievo_breve(db: Session, riga: Rilievo) -> dict:
    albero = _albero(db, riga)
    aperte = 0
    for sezione in albero["sezioni"]:
        if sezione["tipo"] == "strumenti":
            continue
        for voce in sezione["voci"]:
            if voce["mancanti"] and voce["stato"] != "non_applicabile":
                aperte += 1
    return {
        "id": riga.id,
        "titolo": riga.titolo,
        "sito": riga.sito,
        "odoo_opportunity_id": riga.odoo_opportunity_id,
        "stato": riga.stato,
        "modello": riga.modello_codice,
        "creato_il": riga.creato_il.isoformat(),
        "tecnico_nome": riga.tecnico_nome or "",
        "voci_aperte": aperte,
    }
