from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mosaika.models import LeadCache, LeadStato, Utente
from mosaika.odoo.parser import (
    e_condominio,
    etichetta_campo,
    giorni_attesa,
    ha_fotovoltaico,
    parse_descrizione,
    parse_nome_comune,
    stage_name,
    stage_odoo_id,
    stato_da_odoo,
    user_name,
    versione_suggerita,
)
from mosaika.services.whatsapp import (
    messaggio_foto,
    messaggio_video,
    formatta_quando,
    tel_link,
    wa_link,
)
from mosaika.timeutil import ROMA, adesso, come_utc

STATI = (
    "da chiamare",
    "contattato",
    "videochiamata fissata",
    "foto richieste",
    "preventivo da fare",
    "preventivo inviato",
    "vinto",
    "perso",
)
CHIUSI = {"vinto", "perso"}
IN_CORSO = {
    "contattato",
    "videochiamata fissata",
    "foto richieste",
    "preventivo da fare",
    "preventivo inviato",
}
ZONE = ("in zona", "da verificare", "fuori zona")
VERSIONI = ("Essenziale", "Smart", "Solare")
QUALIFICA_VOCI = (
    "auto_parcheggio",
    "edificio",
    "potenza_contatore",
    "fotovoltaico_accumulo",
    "distanza_quadro",
    "uso",
    "tempi",
)
QUALIFICA_ETICHETTE = {
    "auto_parcheggio": "Auto e parcheggio",
    "edificio": "Villetta o condominio",
    "potenza_contatore": "Potenza del contatore",
    "fotovoltaico_accumulo": "Fotovoltaico e accumulo",
    "distanza_quadro": "Distanza quadro–posto auto",
    "uso": "Uso (km, notte o giorno)",
    "tempi": "Tempi",
}
GIRO_VOCI = (
    "contatore",
    "quadro",
    "percorso_cavo",
    "punto_wallbox",
    "inverter",
)
GIRO_ETICHETTE = {
    "contatore": "Contatore",
    "quadro": "Quadro",
    "percorso_cavo": "Percorso del cavo",
    "punto_wallbox": "Punto della wallbox",
    "inverter": "Inverter",
}
FILTRI = ("da_lavorare", "da_chiamare", "in_corso", "chiusi", "tutti")


class LeadNonTrovato(LookupError):
    pass


class DatoNonValido(ValueError):
    pass


def stato_effettivo(cache: LeadCache, lavoro: LeadStato | None) -> str:
    if lavoro and lavoro.stato:
        return lavoro.stato
    return stato_da_odoo(cache.active, stage_name(cache.stage_id))


def zona_effettiva(lavoro: LeadStato | None) -> str:
    if lavoro and lavoro.zona:
        return lavoro.zona
    return "da verificare"


def in_ritardo(giorni: int, stato: str) -> bool:
    return stato == "da chiamare" and giorni > 2


def etichette(zona: str, modulo: dict) -> list[str]:
    tags = []
    if zona == "fuori zona":
        tags.append("fuori zona")
    if ha_fotovoltaico(modulo.get("fotovoltaico")):
        tags.append("ha il fotovoltaico")
    if e_condominio(modulo.get("parcheggio")):
        tags.append("condominio")
    return tags


def passa_filtro(stato: str, filtro: str) -> bool:
    if filtro == "da_lavorare":
        return stato not in CHIUSI
    if filtro == "da_chiamare":
        return stato == "da chiamare"
    if filtro == "in_corso":
        return stato in IN_CORSO
    if filtro == "chiusi":
        return stato in CHIUSI
    if filtro == "tutti":
        return True
    raise DatoNonValido("Filtro non riconosciuto.")


def qualifica_vuota() -> dict:
    return {voce: {"nota": "", "fatto": False} for voce in QUALIFICA_VOCI}


def normalizza_qualifica(data: dict | None, precedente: dict | None = None) -> dict:
    unito = dict(precedente or {})
    if data:
        unito.update(data)
    out = {}
    for voce in QUALIFICA_VOCI:
        raw = unito.get(voce) or {}
        if isinstance(raw, str):
            nota = raw
            fatto = bool(nota.strip())
        elif isinstance(raw, dict):
            nota = str(raw.get("nota") or "")
            fatto = bool(raw.get("fatto")) or bool(nota.strip())
        else:
            nota = ""
            fatto = False
        out[voce] = {"nota": nota.strip(), "fatto": fatto}
    return out


def normalizza_giro(data: dict | None, precedente: dict | None = None) -> dict:
    base = {voce: False for voce in GIRO_VOCI}
    if precedente:
        for voce in GIRO_VOCI:
            base[voce] = bool(precedente.get(voce))
    if data:
        for voce in GIRO_VOCI:
            if voce in data:
                base[voce] = bool(data[voce])
    return base


def _modulo_api(modulo: dict) -> dict:
    return {
        campo: {"chiave": etichetta_campo(campo), "valore": modulo.get(campo)}
        for campo in ("fotovoltaico", "auto", "parcheggio")
    }


def _riga(cache: LeadCache, lavoro: LeadStato | None, momento: datetime) -> dict:
    modulo = parse_descrizione(cache.description)
    nome, comune = parse_nome_comune(cache.name, cache.city)
    stato = stato_effettivo(cache, lavoro)
    zona = zona_effettiva(lavoro)
    giorni = giorni_attesa(cache.create_date, momento)
    return {
        "odoo_lead_id": cache.odoo_lead_id,
        "nome": nome,
        "comune": comune,
        "stato": stato,
        "zona": zona,
        "giorni_attesa": giorni,
        "in_ritardo": in_ritardo(giorni, stato),
        "etichette": etichette(zona, modulo),
        "create_date": come_utc(cache.create_date).strftime("%Y-%m-%d %H:%M:%S"),
        "create_ts": come_utc(cache.create_date).timestamp(),
        "fuori_zona": zona == "fuori zona",
    }


def elenco(db: Session, filtro: str = "da_lavorare") -> dict:
    if filtro not in FILTRI:
        raise DatoNonValido("Filtro non riconosciuto.")
    momento = adesso()
    caches = db.scalars(select(LeadCache)).all()
    stati = {
        row.odoo_lead_id: row
        for row in db.scalars(select(LeadStato)).all()
    }
    righe = [_riga(cache, stati.get(cache.odoo_lead_id), momento) for cache in caches]
    da_chiamare = sum(1 for riga in righe if riga["stato"] == "da chiamare")
    piu_vecchio = max((riga["giorni_attesa"] for riga in righe), default=0)
    visibili = [riga for riga in righe if passa_filtro(riga["stato"], filtro)]
    visibili.sort(key=lambda riga: (riga["fuori_zona"], riga["stato"] != "da chiamare", -riga["create_ts"]))
    for riga in visibili:
        riga.pop("create_ts", None)
        riga.pop("fuori_zona", None)
    letto = max((cache.letto_il for cache in caches), default=None)
    return {
        "filtro": filtro,
        "riepilogo": {
            "totale": len(righe),
            "da_chiamare": da_chiamare,
            "giorni_piu_vecchio": piu_vecchio,
        },
        "letto_il": come_utc(letto).isoformat() if letto else None,
        "leads": visibili,
    }


def _messaggi(nome: str, phone: str | None, mittente: str, video_il: datetime | None) -> dict:
    foto = messaggio_foto(nome, mittente)
    video = None
    video_url = None
    if video_il is not None:
        video = messaggio_video(nome, mittente, formatta_quando(video_il))
        video_url = wa_link(phone, video)
    return {
        "foto": {"testo": foto, "url": wa_link(phone, foto)},
        "video": {"testo": video, "url": video_url},
    }


def scheda(db: Session, odoo_lead_id: int, mittente: str) -> dict:
    cache = db.get(LeadCache, odoo_lead_id)
    if cache is None:
        raise LeadNonTrovato()
    lavoro = db.get(LeadStato, odoo_lead_id)
    momento = adesso()
    modulo = parse_descrizione(cache.description)
    nome, comune = parse_nome_comune(cache.name, cache.city)
    stato = stato_effettivo(cache, lavoro)
    zona = zona_effettiva(lavoro)
    giorni = giorni_attesa(cache.create_date, momento)
    qualifica = normalizza_qualifica(None, lavoro.qualifica if lavoro else None)
    giro = normalizza_giro(None, lavoro.giro if lavoro else None)
    video_il = lavoro.video_il if lavoro else None
    aggiornato_nome = None
    if lavoro and lavoro.aggiornato_da:
        utente = db.get(Utente, lavoro.aggiornato_da)
        aggiornato_nome = utente.nome if utente else None
    return {
        "odoo_lead_id": cache.odoo_lead_id,
        "nome": nome,
        "comune": comune,
        "name_odoo": cache.name,
        "phone": cache.phone,
        "email": cache.email_from,
        "city_odoo": cache.city,
        "stage": stage_name(cache.stage_id) or None,
        "stage_id": stage_odoo_id(cache.stage_id),
        "type": cache.lead_type,
        "assegnatario": user_name(cache.user_id),
        "active": cache.active,
        "archiviato": not cache.active,
        "create_date": come_utc(cache.create_date).strftime("%Y-%m-%d %H:%M:%S"),
        "giorni_attesa": giorni,
        "in_ritardo": in_ritardo(giorni, stato),
        "modulo": _modulo_api(modulo),
        "etichette": etichette(zona, modulo),
        "stato": stato,
        "zona": zona,
        "qualifica": qualifica,
        "qualifica_voci": [
            {"id": voce, "etichetta": QUALIFICA_ETICHETTE[voce]}
            for voce in QUALIFICA_VOCI
        ],
        "versione": lavoro.versione if lavoro else None,
        "versione_suggerita": versione_suggerita(modulo.get("fotovoltaico")),
        "sopralluogo": lavoro.sopralluogo if lavoro else None,
        "video_il": video_il.isoformat() if video_il else None,
        "giro": giro,
        "giro_voci": [
            {"id": voce, "etichetta": GIRO_ETICHETTE[voce]} for voce in GIRO_VOCI
        ],
        "foto_ricevute": bool(lavoro.foto_ricevute) if lavoro else False,
        "note": (lavoro.note if lavoro and lavoro.note else ""),
        "contatti": {
            "tel": tel_link(cache.phone),
            "whatsapp": wa_link(cache.phone),
            "email": f"mailto:{cache.email_from}" if cache.email_from else None,
        },
        "messaggi": _messaggi(nome, cache.phone, mittente, video_il),
        "promemoria_sopralluogo": "15 minuti: 3 conferme, 8 giro, 4 proposta.",
        "promemoria_odoo": (
            "Preventivo, fase e assegnazione si aggiornano in Odoo. "
            "In questa versione il prototipo non scrive su Odoo."
        ),
        "aggiornato_il": lavoro.aggiornato_il.isoformat() if lavoro and lavoro.aggiornato_il else None,
        "aggiornato_da": aggiornato_nome,
        "stati": list(STATI),
        "zone": list(ZONE),
        "versioni": list(VERSIONI),
    }


def _interpreta_video(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=ROMA)
    return value


def aggiorna(db: Session, odoo_lead_id: int, dati: dict, campi: set[str], utente: Utente) -> dict:
    if db.get(LeadCache, odoo_lead_id) is None:
        raise LeadNonTrovato()
    row = db.get(LeadStato, odoo_lead_id)
    if row is None:
        row = LeadStato(odoo_lead_id=odoo_lead_id, foto_ricevute=False)
        db.add(row)

    if "zona" in campi and dati.get("zona") is not None:
        if dati["zona"] not in ZONE:
            raise DatoNonValido("Zona non riconosciuta.")
        row.zona = dati["zona"]
    if "qualifica" in campi and dati.get("qualifica") is not None:
        row.qualifica = normalizza_qualifica(dati["qualifica"], row.qualifica)
    if "versione" in campi:
        versione = dati.get("versione")
        if versione is not None and versione not in VERSIONI:
            raise DatoNonValido("Versione non riconosciuta.")
        row.versione = versione
    if "giro" in campi and dati.get("giro") is not None:
        row.giro = normalizza_giro(dati["giro"], row.giro)
    if "note" in campi:
        note = dati.get("note") or ""
        if len(note) > 20000:
            raise DatoNonValido("Nota troppo lunga.")
        row.note = note
    if "sopralluogo" in campi and dati.get("sopralluogo") is not None:
        if dati["sopralluogo"] not in ("video", "foto"):
            raise DatoNonValido("Sopralluogo non riconosciuto.")
        row.sopralluogo = dati["sopralluogo"]
    if "video_il" in campi:
        row.video_il = _interpreta_video(dati.get("video_il"))
    if "foto_ricevute" in campi and dati.get("foto_ricevute") is not None:
        row.foto_ricevute = bool(dati["foto_ricevute"])
    if "stato" in campi and dati.get("stato"):
        if dati["stato"] not in STATI:
            raise DatoNonValido("Stato non riconosciuto.")
        row.stato = dati["stato"]

    # Le azioni del sopralluogo fissano lo stato, anche se nel payload c'è il selettore.
    if "video_il" in campi and row.video_il is not None:
        row.sopralluogo = "video"
        row.stato = "videochiamata fissata"
    if "sopralluogo" in campi and dati.get("sopralluogo") == "foto" and not row.foto_ricevute:
        row.stato = "foto richieste"
    if "foto_ricevute" in campi and dati.get("foto_ricevute"):
        row.sopralluogo = "foto"
        row.stato = "preventivo da fare"

    row.aggiornato_il = adesso()
    row.aggiornato_da = utente.id
    db.commit()
    return scheda(db, odoo_lead_id, utente.nome)
