import html
import re
from datetime import datetime, timezone

from mosaika.timeutil import come_utc

# Chiavi come arrivano nel HTML di Odoo. In interfaccia gli underscore diventano spazi.
CHIAVI_MODULO = {
    "hai_il_fotovoltaico?": "fotovoltaico",
    "hai_un'auto_elettrica_o_ibrida_plug-in?": "auto",
    "dove_parcheggi_l'auto?": "parcheggio",
}

_ROW = re.compile(
    r"<b>\s*(.*?)\s*</b>\s*(.*?)(?=<br\s*/?>|</p>|</div>|<b>|$)",
    re.IGNORECASE | re.DOTALL,
)


def etichetta_chiave(chiave_odoo: str) -> str:
    return chiave_odoo.replace("_", " ")


def etichetta_campo(campo: str) -> str:
    for chiave, nome in CHIAVI_MODULO.items():
        if nome == campo:
            return etichetta_chiave(chiave)
    return campo


def parse_create_date(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return come_utc(value)
    raw = str(value).strip().replace("T", " ")
    if raw.endswith("Z"):
        raw = raw[:-1]
    raw = raw[:19]
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def parse_nome_comune(name: str | None, city: str | None = None) -> tuple[str, str]:
    """`Meta · 2026-11-wallbox-casa · Nome Cognome · Comune`."""
    parts = [p.strip() for p in (name or "").split("·")]
    nome = ""
    comune = ""
    if len(parts) >= 4:
        nome = parts[2]
        comune = parts[3]
    elif len(parts) == 3:
        nome = parts[2]
    elif name:
        nome = name.strip()
    if not comune and city:
        comune = city.strip()
    return nome, comune


def _norm_chiave(raw: str) -> str:
    key = html.unescape(re.sub(r"<[^>]+>", "", raw))
    key = key.replace("’", "'").replace("`", "'").replace("\xa0", " ")
    key = re.sub(r"\s+", " ", key).strip()
    if key.endswith(":"):
        key = key[:-1].strip()
    key = key.replace(" ", "_")
    return key.casefold()


def _pulisci_valore(raw: str) -> str:
    value = re.sub(r"<[^>]+>", " ", raw)
    value = html.unescape(value).replace("\xa0", " ")
    value = value.strip()
    if value.startswith(":"):
        value = value[1:].strip()
    return re.sub(r"\s+", " ", value).strip()


def parse_descrizione(description: str | None) -> dict[str, str | None]:
    trovato: dict[str, str] = {}
    if description:
        for match in _ROW.finditer(description):
            key = _norm_chiave(match.group(1))
            value = _pulisci_valore(match.group(2))
            if key and value:
                trovato[key] = value
    modulo: dict[str, str | None] = {
        "fotovoltaico": None,
        "auto": None,
        "parcheggio": None,
    }
    for chiave, campo in CHIAVI_MODULO.items():
        modulo[campo] = trovato.get(chiave.casefold())
    return modulo


def stage_name(stage_id) -> str:
    if isinstance(stage_id, (list, tuple)) and len(stage_id) >= 2 and stage_id[1]:
        return str(stage_id[1])
    if isinstance(stage_id, dict) and stage_id.get("name"):
        return str(stage_id["name"])
    return ""


def stage_odoo_id(stage_id):
    if isinstance(stage_id, (list, tuple)) and stage_id:
        return stage_id[0]
    if isinstance(stage_id, dict):
        return stage_id.get("id")
    return None


def user_name(user_id) -> str | None:
    if isinstance(user_id, (list, tuple)) and len(user_id) >= 2 and user_id[1]:
        return str(user_id[1])
    if isinstance(user_id, dict) and user_id.get("name"):
        return str(user_id["name"])
    return None


def stato_da_odoo(active: bool, stage: str) -> str:
    if not active:
        return "perso"
    nome = (stage or "").strip()
    if nome == "Won":
        return "vinto"
    if nome in ("Proposta Inviata", "Negoziazione"):
        return "preventivo inviato"
    if nome == "Fissare Survey / Info":
        return "contattato"
    return "da chiamare"


def giorni_attesa(create_date: datetime, momento: datetime) -> int:
    delta = come_utc(momento) - come_utc(create_date)
    return max(delta.days, 0)


def ha_fotovoltaico(valore: str | None) -> bool:
    if not valore:
        return False
    return valore.strip().casefold() in {"sì", "si"}


def e_condominio(parcheggio: str | None) -> bool:
    if not parcheggio:
        return False
    return "condominio" in parcheggio.casefold()


def versione_suggerita(fotovoltaico: str | None) -> str:
    """Solare se ha il fotovoltaico, altrimenti Smart.

    Essenziale resta una scelta della persona, quando il cliente vuole
    solo ricaricare spendendo poco.
    """
    if ha_fotovoltaico(fotovoltaico):
        return "Solare"
    return "Smart"
