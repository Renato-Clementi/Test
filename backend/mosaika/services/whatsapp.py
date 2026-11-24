import re
from datetime import datetime
from urllib.parse import quote

from mosaika.timeutil import ROMA

_GIORNI = (
    "lunedì",
    "martedì",
    "mercoledì",
    "giovedì",
    "venerdì",
    "sabato",
    "domenica",
)
_MESI = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)


def numero_wa(phone: str | None) -> str | None:
    """Cifre con prefisso 39, senza «+», come le vuole wa.me."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if digits.startswith("0039"):
        digits = digits[2:]
    if not digits.startswith("39"):
        digits = "39" + digits.lstrip("0")
    return digits


def tel_link(phone: str | None) -> str | None:
    numero = numero_wa(phone)
    if not numero:
        return None
    return f"tel:+{numero}"


def wa_link(phone: str | None, testo: str | None = None) -> str | None:
    numero = numero_wa(phone)
    if not numero:
        return None
    url = f"https://wa.me/{numero}"
    if testo:
        url = f"{url}?text={quote(testo)}"
    return url


def formatta_quando(value: datetime) -> str:
    locale = value.astimezone(ROMA)
    giorno = _GIORNI[locale.weekday()]
    mese = _MESI[locale.month - 1]
    return f"{giorno} {locale.day} {mese} alle {locale:%H:%M}"


def messaggio_foto(nome: str, mittente: str) -> str:
    return (
        f"Buongiorno {nome}, sono {mittente} di BABOO. "
        "Grazie per la richiesta sulla ricarica a casa. "
        "Per prepararle il preventivo senza sopralluogo mi servono 5 foto:\n"
        "1. il contatore, con la targhetta leggibile "
        "(o la prima pagina della bolletta con la potenza impegnata);\n"
        "2. il quadro elettrico, aperto;\n"
        "3. il punto dove vorrebbe la wallbox;\n"
        "4. il percorso dal quadro al posto auto "
        "(anche 2-3 foto o un breve video);\n"
        "5. se c'è, l'inverter del fotovoltaico.\n"
        "Se preferisce, possiamo fare una videochiamata di 10 minuti. Grazie!"
    )


def messaggio_video(nome: str, mittente: str, quando: str) -> str:
    return (
        f"Buongiorno {nome}, sono {mittente} di BABOO. "
        f"Le confermo la videochiamata su WhatsApp {quando}: "
        "15 minuti per vedere insieme contatore, quadro e posto auto, "
        "così le preparo il preventivo senza sopralluogo. A presto!"
    )
