"""ZIP di un rilievo: cartelle per sezione, file rinominati, riepilogo e relazione."""

from __future__ import annotations

import csv
import html
import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timezone

from mosaika.timeutil import come_roma

ORDINE_CAPITOLI = ("1", "1·2", "2", "3", "3·4", "3·5", "4", "5", "7", "esclusa", "—")


def nome_zip(rilievo: dict) -> str:
    pezzi = ["sopralluogo", str(rilievo["id"])]
    if rilievo.get("odoo_opportunity_id"):
        pezzi.append(f"opp{rilievo['odoo_opportunity_id']}")
    pezzi.append(_slug(rilievo.get("sito") or "sito"))
    return "-".join(pezzo for pezzo in pezzi if pezzo) + ".zip"


def costruisci_zip(rilievo: dict, storage) -> bytes:
    pubblico = _senza_chiavi(rilievo)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archivio:
        archivio.writestr("riepilogo.json", _json(pubblico), compress_type=zipfile.ZIP_DEFLATED)
        archivio.writestr("riepilogo.csv", _csv(pubblico), compress_type=zipfile.ZIP_DEFLATED)
        archivio.writestr("relazione.html", _html(pubblico), compress_type=zipfile.ZIP_DEFLATED)
        for sezione in rilievo["sezioni"]:
            for voce in sezione["voci"]:
                for file in voce["file"]:
                    cartella = sezione.get("prefisso") or sezione["codice"]
                    nome = f"{cartella}/{file['nome_assegnato']}"
                    percorso = storage.open_path(file["storage_key"])
                    archivio.write(percorso, nome, compress_type=zipfile.ZIP_STORED)
                    archivio.writestr(
                        nome + ".json",
                        _json(_sidecar(sezione, voce, file)),
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
        if rilievo.get("firma_key"):
            percorso = storage.open_path(rilievo["firma_key"])
            archivio.write(percorso, "chiusura/firma.png", compress_type=zipfile.ZIP_STORED)
    return buffer.getvalue()


def _sidecar(sezione: dict, voce: dict, file: dict) -> dict:
    return {
        "nome": file["nome_assegnato"],
        "nome_originale": file["nome_originale"],
        "tipo": file["tipo"],
        "content_type": file["content_type"],
        "byte": file["byte_size"],
        "sha256": file["sha256"],
        "sezione": sezione["codice"],
        "prefisso": sezione.get("prefisso"),
        "voce": voce["testo"],
        "capitolo": voce["capitolo"],
        "capitolo_etichetta": voce["capitolo_etichetta"],
        "timestamp": file["creato_il"],
        "autore": file["autore"],
        "gps": file["gps"],
        "vista_insieme": file["vista_insieme"],
        "consenso": file["consenso"],
        "consenso_nome": file["consenso_nome"],
    }


def _json(dati: dict) -> str:
    return json.dumps(dati, ensure_ascii=False, indent=2)


def _csv(rilievo: dict) -> str:
    buffer = io.StringIO()
    colonne = [
        "sezione",
        "prefisso",
        "voce",
        "testo",
        "capitolo",
        "stato",
        "evidenze",
        "mancanti",
        "nota",
        "misure",
        "file",
        "file_originali",
        "chi_invia",
        "entro_il",
    ]
    writer = csv.DictWriter(buffer, fieldnames=colonne, delimiter=";")
    writer.writeheader()
    for sezione in rilievo["sezioni"]:
        for voce in sezione["voci"]:
            misure = " | ".join(_misura_testo(misura) for misura in voce["misure"])
            writer.writerow(
                {
                    "sezione": sezione["titolo"],
                    "prefisso": sezione.get("prefisso") or "",
                    "voce": voce["ordine"],
                    "testo": voce["testo"],
                    "capitolo": voce["capitolo_etichetta"],
                    "stato": voce["stato"],
                    "evidenze": " ".join(voce["evidenze"]),
                    "mancanti": " ".join(voce["mancanti"]),
                    "nota": voce["testo_nota"],
                    "misure": misure,
                    "file": " ".join(file["nome_assegnato"] for file in voce["file"]),
                    "file_originali": " ".join(file["nome_originale"] for file in voce["file"]),
                    "chi_invia": voce["chi_invia"],
                    "entro_il": voce["entro_il"] or "",
                }
            )
    return "\ufeff" + buffer.getvalue()


def _misura_testo(misura: dict) -> str:
    pezzi = []
    if misura.get("etichetta"):
        pezzi.append(misura["etichetta"])
    pezzi.append(f"{misura['valore']} {misura['unita']}".strip())
    if misura.get("rilevata_il"):
        pezzi.append(_ora(misura["rilevata_il"]))
    if misura.get("temperatura_esterna"):
        pezzi.append(f"esterna {misura['temperatura_esterna']} °C")
    return ", ".join(pezzi)


def _ora(valore) -> str:
    if isinstance(valore, datetime):
        momento = valore
    elif isinstance(valore, str) and valore:
        try:
            momento = datetime.fromisoformat(valore.replace("Z", "+00:00"))
        except ValueError:
            return valore
    else:
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return come_roma(momento).strftime("%d/%m/%Y %H:%M")


def _senza_chiavi(rilievo: dict) -> dict:
    copia = {chiave: valore for chiave, valore in rilievo.items() if chiave != "firma_key"}
    sezioni = []
    for sezione in rilievo["sezioni"]:
        voci = []
        for voce in sezione["voci"]:
            file = [{k: v for k, v in file.items() if k != "storage_key"} for file in voce["file"]]
            voci.append({**voce, "file": file})
        sezioni.append({**sezione, "voci": voci})
    copia["sezioni"] = sezioni
    return copia


def _html(rilievo: dict) -> str:
    gruppi: dict[str, list[tuple[dict, dict]]] = {}
    for sezione in rilievo["sezioni"]:
        if sezione["tipo"] in ("strumenti", "chiusura"):
            continue
        for voce in sezione["voci"]:
            gruppi.setdefault(voce["capitolo"] or "—", []).append((sezione, voce))
    chiavi = [cap for cap in ORDINE_CAPITOLI if cap in gruppi]
    chiavi += [cap for cap in gruppi if cap not in chiavi]
    blocchi = []
    for capitolo in chiavi:
        voci = []
        for sezione, voce in gruppi[capitolo]:
            voci.append(_voce_html(sezione, voce))
        titolo = voce_etichetta(capitolo)
        if titolo == "—":
            titolo = "Senza capitolo"
        blocchi.append(f"<section><h2>{html.escape(titolo)}</h2>{''.join(voci)}</section>")
    chiusura = rilievo.get("chiusura") or {}
    strumenti = []
    for sezione in rilievo["sezioni"]:
        if sezione["tipo"] != "strumenti":
            continue
        for voce in sezione["voci"]:
            segno = "sì" if voce["stato"] == "fatto" else "no"
            strumenti.append(f"<li>{html.escape(voce['testo'])} — {segno}</li>")
    opportunita = rilievo.get("odoo_opportunity_id")
    testata = (
        f"<p>Sito: {html.escape(rilievo['sito'])}<br>"
        f"Opportunità: {html.escape(str(opportunita) if opportunita else '—')}<br>"
        f"Modello: {html.escape(rilievo['modello'])} · rev. {html.escape(rilievo['revisione'])}<br>"
        f"Tecnico: {html.escape(rilievo.get('tecnico_nome') or '—')}<br>"
        f"Stato: {html.escape(rilievo['stato'])}</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Sopralluogo {html.escape(rilievo['sito'])}</title>
<style>
  body {{ font-family: "Work Sans", sans-serif; color: #3C4348; margin: 24px; }}
  h1 {{ font-weight: 200; color: #374350; }}
  h2 {{ font-weight: 200; color: #374350; border-bottom: 1px solid #D6E1EA; }}
  article {{ border: 1px solid #D6E1EA; border-radius: 12px; padding: 12px 16px; margin: 12px 0; }}
  .manca {{ color: #B42318; }}
  .ok {{ color: #1F6B45; }}
  .meta {{ font-family: ui-monospace, monospace; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: #5B6670; }}
</style>
</head>
<body>
<p class="meta">MOSAIKA · Sopralluogo · relazione per il capitolato</p>
<h1>{html.escape(rilievo['titolo'])}</h1>
{testata}
<h2>Prima di andare via</h2>
{_chiusura_html(chiusura)}
{''.join(blocchi)}
<h2>Strumenti</h2>
<ul>{''.join(strumenti)}</ul>
</body>
</html>
"""


def voce_etichetta(capitolo: str) -> str:
    if not capitolo or capitolo == "—":
        return "—"
    if capitolo == "esclusa":
        return "CAP. esclusa"
    return "CAP. " + capitolo.replace("·", " · ")


def _voce_html(sezione: dict, voce: dict) -> str:
    mancanti = ", ".join(voce["mancanti"]) or "nessuna"
    classe = "manca" if voce["mancanti"] and voce["stato"] != "non_applicabile" else "ok"
    file = "".join(
        f"<li>{html.escape(file['nome_assegnato'])} "
        f"<span class=\"meta\">({html.escape(file['nome_originale'])}, {html.escape(file['autore'])})</span></li>"
        for file in voce["file"]
    ) or "<li>—</li>"
    misure = "".join(f"<li>{html.escape(_misura_testo(misura))}</li>" for misura in voce["misure"]) or "<li>—</li>"
    nota = html.escape(voce["testo_nota"] or "—")
    return (
        f"<article><p class=\"meta\">{html.escape(sezione['titolo'])} · {html.escape(voce['stato'])}</p>"
        f"<p><strong>{html.escape(voce['testo'])}</strong></p>"
        f"<p class=\"{classe}\">Mancanti: {html.escape(mancanti)}</p>"
        f"<p>Nota: {nota}</p>"
        f"<p>Misure</p><ul>{misure}</ul>"
        f"<p>File</p><ul>{file}</ul></article>"
    )


def _chiusura_html(chiusura: dict) -> str:
    insieme = chiusura.get("senza_foto_insieme") or []
    misure = chiusura.get("senza_misure") or []
    documenti = chiusura.get("documenti_mancanti") or []
    temp = "complete" if chiusura.get("temperature_complete") else "mancanti"
    posizione = "fotografata" if chiusura.get("posizione_fotografata") else "senza foto"
    righe_doc = "".join(
        f"<li>{html.escape(doc['testo'])} — "
        f"{html.escape(doc.get('chi_invia') or 'chi invia?')} — "
        f"{html.escape(doc.get('entro_il') or 'senza data')}</li>"
        for doc in documenti
    ) or "<li>Nessun documento in sospeso.</li>"
    insieme_testo = ", ".join(html.escape(s["titolo"]) for s in insieme) or "nessuno"
    misure_testo = ", ".join(html.escape(s["titolo"]) for s in misure) or "nessuno"
    return (
        f"<ul><li>Capitoli senza foto d'insieme: {insieme_testo}</li>"
        f"<li>Capitoli con misure mancanti: {misure_testo}</li>"
        f"<li>Temperature di mandata e ritorno: {temp}</li>"
        f"<li>Posizione dell'unità esterna: {posizione}</li></ul>"
        f"<p>Documenti mancanti</p><ul>{righe_doc}</ul>"
    )


def _slug(testo: str) -> str:
    norm = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode("ascii")
    pulito = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return (pulito or "sito")[:40]
