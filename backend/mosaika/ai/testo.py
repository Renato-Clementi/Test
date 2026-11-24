import re

_BLOCCO = re.compile(r"\[VALIDATA\]\n(.*?)\[/VALIDATA\]", re.DOTALL)
_FRASE = re.compile(r"(?<=[.!?])\s+")
_PREZZO = re.compile(r"€|\beuro\b|\d+\s*%", re.IGNORECASE)


def spezza_frasi(testo: str) -> list[str]:
    parti = _FRASE.split(testo.strip())
    return [p.strip() for p in parti if p.strip()]


def componi_frasi(testi: list[str]) -> str:
    """Due-quattro frasi prese solo dai testi validate, senza aggiungere fatti."""
    frasi: list[str] = []
    for testo in testi:
        frasi.extend(spezza_frasi(testo))
    frasi = frasi[:4]
    if not frasi:
        return ""
    if len(frasi) == 1:
        frasi.append("È una risposta già validata nel registro.")
    return " ".join(frasi[:4])


def estrai_blocchi_validati(messaggio: str) -> list[str]:
    return [b.strip() for b in _BLOCCO.findall(messaggio) if b.strip()]


def inventa_prezzo_o_percentuale(output: str, fonti: list[str]) -> bool:
    base = "\n".join(fonti)
    return bool(_PREZZO.search(output)) and not bool(_PREZZO.search(base))
