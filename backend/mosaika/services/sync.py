from sqlalchemy import delete, select

from mosaika.models import LeadCache
from mosaika.odoo.parser import parse_create_date
from mosaika.timeutil import adesso


def _testo(value):
    if value is None or value is False:
        return None
    if isinstance(value, str):
        testo = value.strip()
        return testo or None
    return value


def _relazione(value):
    if not value or value is False:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return None


def sincronizza_lead(db, source) -> int:
    """Rilegge la fonte e aggiorna solo `lead_cache`. Non tocca lo stato di lavoro."""
    records = source.search_read_wallbox_leads()
    momento = adesso()
    visti: set[int] = set()
    for record in records:
        odoo_id = int(record["id"])
        visti.add(odoo_id)
        row = db.get(LeadCache, odoo_id)
        if row is None:
            row = LeadCache(odoo_lead_id=odoo_id, name="", create_date=momento, letto_il=momento)
            db.add(row)
        row.name = _testo(record.get("name")) or ""
        row.description = _testo(record.get("description"))
        row.phone = _testo(record.get("phone"))
        row.email_from = _testo(record.get("email_from"))
        row.city = _testo(record.get("city"))
        row.stage_id = _relazione(record.get("stage_id"))
        tipo = record.get("type")
        row.lead_type = tipo if isinstance(tipo, str) else None
        row.user_id = _relazione(record.get("user_id"))
        row.create_date = parse_create_date(record.get("create_date"))
        row.active = bool(record.get("active", True))
        row.letto_il = momento
    if visti:
        db.execute(delete(LeadCache).where(LeadCache.odoo_lead_id.not_in(sorted(visti))))
    else:
        db.execute(delete(LeadCache))
    db.commit()
    return len(visti)


def ultimo_letto(db):
    righe = db.scalars(select(LeadCache.letto_il)).all()
    if not righe:
        return None
    return max(righe)
