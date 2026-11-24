import logging
import re
import unicodedata

from sqlalchemy import select

from mosaika.ai.testo import componi_frasi, inventa_prezzo_o_percentuale
from mosaika.models import Obiezione

log = logging.getLogger("mosaika.assistente")

PROMPT_VERSION = "obiezioni_v1"

# Frase del brief, usata quando nessuna risposta validata copre la domanda.
FRASE_RINVIO = (
    "Non c'è ancora una risposta validata. Di' al cliente che verifichi con il tecnico "
    "e aggiungi la domanda al registro."
)

_STOP = {
    "che", "chi", "cui", "con", "col", "per", "tra", "fra", "dal", "dallo",
    "della", "delle", "dello", "degli", "dei", "del", "una", "uno", "sul",
    "sulla", "sulle", "sugli", "come", "dove", "quando", "quanto", "quali",
    "questo", "questa", "quello", "quella", "sono", "siamo", "essere", "avere",
    "non", "piu", "più", "gia", "già", "ancora", "solo", "anche", "oppure",
    "perche", "perché", "cosa", "c'è", "puo", "può", "devono", "deve", "nel",
    "nella", "negli", "nelle", "alla", "alle", "agli", "allo", "dall", "dell",
    "un", "il", "lo", "la", "i", "gli", "le", "di", "a", "da", "in", "su",
    "ma", "se", "o", "ed", "ad", "al", "ai", "mi", "ti", "ci", "vi", "si",
    "mio", "mia", "tuo", "tua", "suo", "sua", "noi", "voi", "loro", "c'e",
    "sta", "sto", "fare", "fatto", "essere", "era", "ho", "hai", "ha",
    "cliente", "clienti",
}

# Parole troppo generiche per decidere da sole che una risposta «copre» la domanda.
_GENERICHE = {
    "wallbox",
    "baboo",
    "installazione",
    "installare",
    "ricarica",
    "ricaricare",
    "elettrica",
    "elettrico",
    "elettrica",
    "casa",
    "auto",
    "domanda",
    "risposta",
}


def carica_prompt(settings) -> str:
    path = settings.prompts_path() / "obiezioni_v1.md"
    return path.read_text(encoding="utf-8")


def tokenizza(testo: str) -> set[str]:
    normale = unicodedata.normalize("NFKD", testo.casefold())
    normale = "".join(c for c in normale if not unicodedata.combining(c))
    parole = re.findall(r"[a-z0-9']{3,}", normale)
    return {p for p in parole if p not in _STOP}


def _rilevanti(domanda: str, rows: list[Obiezione]) -> list[Obiezione]:
    richiesti = tokenizza(domanda)
    if not richiesti:
        return []
    candidati = []
    for row in rows:
        if not row.validata or not (row.risposta or "").strip():
            continue
        presenti = tokenizza(f"{row.domanda}\n{row.risposta}")
        comuni = richiesti & presenti
        utili = {t for t in comuni if t not in _GENERICHE}
        if len(utili) >= 2 or any(len(t) >= 8 for t in utili):
            punteggio = len(utili) * 10 + sum(len(t) for t in utili)
            candidati.append((punteggio, row))
    candidati.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in candidati[:3]]


def _messaggio(domanda: str, fonti: list[Obiezione]) -> str:
    blocchi = []
    for row in fonti:
        blocchi.append(f"[VALIDATA]\n{row.risposta.strip()}\n[/VALIDATA]")
    return (
        f"Domanda del cliente:\n{domanda.strip()}\n\n"
        "Usa solo queste risposte validate.\n\n"
        + "\n".join(blocchi)
    )


def rispondi(db, settings, provider, domanda: str) -> dict:
    testo = (domanda or "").strip()
    if not testo:
        raise ValueError("La domanda è vuota.")
    if len(testo) > 4000:
        raise ValueError("Domanda troppo lunga.")
    rows = db.scalars(select(Obiezione)).all()
    fonti = _rilevanti(testo, rows)
    if not fonti:
        return {
            "risposta": FRASE_RINVIO,
            "fallback": True,
            "fonti": [],
            "prompt_version": PROMPT_VERSION,
            "provider": "nessuno",
        }
    system = carica_prompt(settings)
    user = _messaggio(testo, fonti)
    testi = [row.risposta.strip() for row in fonti]
    try:
        uscita = (provider.complete(system=system, user=user) or "").strip()
    except Exception:
        log.exception("Provider AI non disponibile, uso le risposte validate")
        uscita = ""
    if not uscita or inventa_prezzo_o_percentuale(uscita, testi):
        uscita = componi_frasi(testi)
        nome_provider = "validate"
    else:
        nome_provider = getattr(provider, "name", "sconosciuto")
    if not uscita:
        return {
            "risposta": FRASE_RINVIO,
            "fallback": True,
            "fonti": [],
            "prompt_version": PROMPT_VERSION,
            "provider": "nessuno",
        }
    return {
        "risposta": uscita,
        "fallback": False,
        "fonti": [row.id for row in fonti],
        "prompt_version": PROMPT_VERSION,
        "provider": nome_provider,
    }
