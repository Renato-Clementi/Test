from sqlalchemy import or_, select

from mosaika.auth import puo_validare
from mosaika.models import Obiezione, Utente
from mosaika.timeutil import adesso


class NonAutorizzato(PermissionError):
    pass


class DatoNonValido(ValueError):
    pass


class ObiezioneNonTrovata(LookupError):
    pass


def badge(row: Obiezione) -> str:
    if row.validata:
        return "validata"
    if not (row.risposta or "").strip():
        return "senza risposta"
    return "in bozza"


def _nome(db, utente_id: int | None) -> str | None:
    if not utente_id:
        return None
    utente = db.get(Utente, utente_id)
    return utente.nome if utente else None


def serializza(db, row: Obiezione) -> dict:
    return {
        "id": row.id,
        "domanda": row.domanda,
        "risposta": row.risposta or "",
        "validata": row.validata,
        "badge": badge(row),
        "comune": row.comune,
        "creata_il": row.creata_il.isoformat(),
        "creata_da": _nome(db, row.creata_da),
        "validata_da": _nome(db, row.validata_da),
        "validata_il": row.validata_il.isoformat() if row.validata_il else None,
    }


def elenco(db, q: str | None = None) -> list[dict]:
    query = select(Obiezione)
    testo = (q or "").strip()
    if testo:
        like = f"%{testo.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        query = query.where(
            or_(
                Obiezione.domanda.ilike(like, escape="\\"),
                Obiezione.risposta.ilike(like, escape="\\"),
                Obiezione.comune.ilike(like, escape="\\"),
            )
        )
    query = query.order_by(Obiezione.validata.desc(), Obiezione.creata_il.desc())
    return [serializza(db, row) for row in db.scalars(query).all()]


def _controlla_testi(domanda: str | None, risposta: str | None) -> None:
    if domanda is not None and not domanda.strip():
        raise DatoNonValido("La domanda è vuota.")
    if domanda is not None and len(domanda) > 4000:
        raise DatoNonValido("Domanda troppo lunga.")
    if risposta is not None and len(risposta) > 8000:
        raise DatoNonValido("Risposta troppo lunga.")


def crea(db, dati: dict, utente: Utente) -> dict:
    domanda = (dati.get("domanda") or "").strip()
    _controlla_testi(domanda, dati.get("risposta"))
    risposta = dati.get("risposta")
    validata = bool(dati.get("validata"))
    if not puo_validare(utente.ruolo):
        if (risposta or "").strip() or validata:
            raise NonAutorizzato(
                "Solo tecnico e admin possono scrivere o validare una risposta."
            )
        risposta = None
        validata = False
    if validata and not (risposta or "").strip():
        raise DatoNonValido("Non si valida una risposta vuota.")
    row = Obiezione(
        domanda=domanda,
        risposta=(risposta or "").strip() or None,
        validata=validata,
        comune=(dati.get("comune") or "").strip() or None,
        creata_il=adesso(),
        creata_da=utente.id,
    )
    if validata:
        row.validata_da = utente.id
        row.validata_il = adesso()
    db.add(row)
    db.commit()
    db.refresh(row)
    return serializza(db, row)


def aggiorna(db, obiezione_id: int, dati: dict, campi: set[str], utente: Utente) -> dict:
    row = db.get(Obiezione, obiezione_id)
    if row is None:
        raise ObiezioneNonTrovata()
    tocca_risposta = "risposta" in campi
    tocca_validata = "validata" in campi
    if not puo_validare(utente.ruolo) and (tocca_risposta or tocca_validata):
        raise NonAutorizzato(
            "Solo tecnico e admin possono modificare o validare una risposta."
        )
    if "domanda" in campi:
        domanda = (dati.get("domanda") or "").strip()
        _controlla_testi(domanda, None)
        row.domanda = domanda
    if "comune" in campi:
        row.comune = (dati.get("comune") or "").strip() or None
    risposta_cambiata = False
    if tocca_risposta:
        risposta = dati.get("risposta") or ""
        _controlla_testi(None, risposta)
        nuova = risposta.strip()
        risposta_cambiata = nuova != (row.risposta or "")
        row.risposta = nuova or None
    if risposta_cambiata and not (tocca_validata and dati.get("validata")):
        row.validata = False
        row.validata_da = None
        row.validata_il = None
    if tocca_validata:
        if dati.get("validata"):
            if not (row.risposta or "").strip():
                raise DatoNonValido("Non si valida una risposta vuota.")
            row.validata = True
            row.validata_da = utente.id
            row.validata_il = adesso()
        else:
            row.validata = False
            row.validata_da = None
            row.validata_il = None
    db.commit()
    return serializza(db, row)
