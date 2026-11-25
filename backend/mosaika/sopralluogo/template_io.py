"""Un modello di checklist è un documento YAML o JSON, non codice."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

EVIDENZE = ("F", "V", "A", "M", "T", "D")
TIPI_SEZIONE = ("documenti", "strumenti", "raccolta", "chiusura")
_CODICE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEZIONE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")
_PREFISSO = re.compile(r"^[A-Z]{2,6}$")
_CHIAVE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ModelloNonValido(ValueError):
    pass


def carica_yaml(path: Path) -> dict:
    dati = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(dati, dict):
        raise ModelloNonValido("Il modello deve essere un oggetto.")
    return normalizza(dati)


def normalizza(dati: dict) -> dict:
    if not isinstance(dati, dict):
        raise ModelloNonValido("Il modello deve essere un oggetto.")
    codice = str(dati.get("codice") or "").strip()
    if not _CODICE.match(codice):
        raise ModelloNonValido("Codice modello non valido: usa lettere minuscole, numeri e trattini.")
    titolo = str(dati.get("titolo") or "").strip()
    if not titolo or len(titolo) > 200:
        raise ModelloNonValido("Manca il titolo del modello, oppure è troppo lungo.")
    sito = str(dati.get("sito") or "").strip()
    if len(sito) > 200:
        raise ModelloNonValido("Il sito del modello è troppo lungo.")
    revisione = str(dati.get("revisione") or "1").strip() or "1"
    if len(revisione) > 16:
        raise ModelloNonValido("Revisione troppo lunga.")
    opportunita = dati.get("odoo_opportunity_id")
    if opportunita in ("", None):
        opportunita = None
    else:
        try:
            opportunita = int(opportunita)
        except (TypeError, ValueError) as exc:
            raise ModelloNonValido("L'id opportunità deve essere un numero.") from exc
        if opportunita <= 0:
            raise ModelloNonValido("L'id opportunità deve essere positivo.")
    sezioni_in = dati.get("sezioni")
    if not isinstance(sezioni_in, list) or not sezioni_in:
        raise ModelloNonValido("Il modello non ha sezioni.")
    if len(sezioni_in) > 40:
        raise ModelloNonValido("Troppe sezioni.")
    sezioni = []
    codici = set()
    prefissi = set()
    voci_totali = 0
    for indice, grezza in enumerate(sezioni_in, start=1):
        sezione = _sezione(grezza, indice)
        if sezione["codice"] in codici:
            raise ModelloNonValido(f"Codice sezione ripetuto: {sezione['codice']}.")
        codici.add(sezione["codice"])
        if sezione["prefisso"]:
            if sezione["prefisso"] in prefissi:
                raise ModelloNonValido(f"Prefisso file ripetuto: {sezione['prefisso']}.")
            prefissi.add(sezione["prefisso"])
        voci_totali += len(sezione["voci"])
        sezioni.append(sezione)
    if voci_totali > 400:
        raise ModelloNonValido("Troppe voci.")
    if voci_totali == 0:
        raise ModelloNonValido("Il modello non ha voci.")
    return {
        "codice": codice,
        "titolo": titolo,
        "sito": sito,
        "revisione": revisione,
        "odoo_opportunity_id": opportunita,
        "perimetro": _testo(dati.get("perimetro"), 2000),
        "istruzioni": _testo(dati.get("istruzioni"), 4000),
        "sezioni": sezioni,
    }


def _testo(valore, massimo: int) -> str | None:
    if valore is None:
        return None
    testo = str(valore).strip()
    if not testo:
        return None
    if len(testo) > massimo:
        raise ModelloNonValido("Un testo del modello è troppo lungo.")
    return testo


def _sezione(grezza, ordine: int) -> dict:
    if not isinstance(grezza, dict):
        raise ModelloNonValido("Sezione non valida.")
    codice = str(grezza.get("codice") or "").strip()
    if not _SEZIONE.match(codice):
        raise ModelloNonValido(f"Codice sezione non valido vicino alla posizione {ordine}.")
    titolo = str(grezza.get("titolo") or "").strip()
    if not titolo or len(titolo) > 200:
        raise ModelloNonValido(f"Manca il titolo della sezione {codice}.")
    tipo = str(grezza.get("tipo") or "").strip()
    if tipo not in TIPI_SEZIONE:
        raise ModelloNonValido(f"Tipo sezione sconosciuto in {codice}.")
    prefisso = grezza.get("prefisso")
    if prefisso in ("", None):
        prefisso = None
    else:
        prefisso = str(prefisso).strip()
        if not _PREFISSO.match(prefisso):
            raise ModelloNonValido(f"Prefisso file non valido in {codice}.")
    if tipo == "strumenti" and prefisso:
        raise ModelloNonValido(f"La sezione strumenti {codice} non porta un prefisso file.")
    voci_in = grezza.get("voci") or []
    if not isinstance(voci_in, list) or not voci_in:
        raise ModelloNonValido(f"La sezione {codice} non ha voci.")
    return {
        "ordine": ordine,
        "codice": codice,
        "titolo": titolo,
        "sottotitolo": _testo(grezza.get("sottotitolo"), 300),
        "prefisso": prefisso,
        "tipo": tipo,
        "voci": [_voce(voce, codice, indice) for indice, voce in enumerate(voci_in, start=1)],
    }


def _voce(grezza, sezione: str, ordine: int) -> dict:
    if not isinstance(grezza, dict):
        raise ModelloNonValido(f"Voce non valida in {sezione}.")
    testo = str(grezza.get("testo") or "").strip()
    if not testo or len(testo) > 1000:
        raise ModelloNonValido(f"Testo voce mancante o troppo lungo in {sezione}.")
    evidenze = []
    for lettera in grezza.get("evidenze") or []:
        codice = str(lettera).strip().upper()
        if codice not in EVIDENZE:
            raise ModelloNonValido(f"Evidenza sconosciuta «{lettera}» in {sezione}.")
        if codice not in evidenze:
            evidenze.append(codice)
    capitolo = str(grezza.get("capitolo") or "—").strip() or "—"
    if len(capitolo) > 32:
        raise ModelloNonValido(f"Capitolo troppo lungo in {sezione}.")
    unita = _testo(grezza.get("unita_suggerita"), 32)
    try:
        minime = int(grezza.get("misure_minime") or 1)
    except (TypeError, ValueError) as exc:
        raise ModelloNonValido(f"misure_minime non è un numero in {sezione}.") from exc
    if minime < 1 or minime > 20:
        raise ModelloNonValido(f"misure_minime fuori scala in {sezione}.")
    chiave = grezza.get("chiave")
    if chiave in ("", None):
        chiave = None
    else:
        chiave = str(chiave).strip()
        if not _CHIAVE.match(chiave):
            raise ModelloNonValido(f"Chiave voce non valida in {sezione}.")
    etichette = []
    for etichetta in grezza.get("etichette") or []:
        pulita = str(etichetta).strip()
        if pulita and pulita not in etichette:
            etichette.append(pulita[:80])
    return {
        "ordine": ordine,
        "testo": testo,
        "evidenze": evidenze,
        "capitolo": capitolo,
        "unita_suggerita": unita,
        "misure_minime": minime,
        "temperatura": bool(grezza.get("temperatura")),
        "con_ora": bool(grezza.get("con_ora")),
        "consenso_richiesto": bool(grezza.get("consenso_richiesto")),
        "chiave": chiave,
        "ripetibile": bool(grezza.get("ripetibile")),
        "etichette": etichette,
    }
