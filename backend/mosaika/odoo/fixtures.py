"""Lead di esempio nel formato descritto dal brief.

Servono a far girare l'app e i test senza credenziali Odoo.
Le date sono UTC, nel formato `YYYY-MM-DD HH:MM:SS` di Odoo.
"""

from __future__ import annotations


def _html(fotovoltaico: str, auto: str, parcheggio: str, separatore: str = "p") -> str:
    righe = [
        ("hai_il_fotovoltaico?", fotovoltaico),
        ("hai_un'auto_elettrica_o_ibrida_plug-in?", auto),
        ("dove_parcheggi_l'auto?", parcheggio),
    ]
    if separatore == "br":
        corpo = "<br>".join(f"<b>{k}:</b> {v}" for k, v in righe)
        return f"<div>{corpo}</div>"
    corpo = "".join(f"<p><b>{k}:</b> {v}</p>" for k, v in righe)
    return f"<div>{corpo}</div>"


def _lead(
    odoo_id: int,
    persona: str,
    comune: str,
    *,
    phone: str,
    email: str | None,
    stage: list,
    create_date: str,
    active: bool = True,
    fotovoltaico: str,
    auto: str,
    parcheggio: str,
    user: list | bool = False,
    separatore: str = "p",
    city: str | None = None,
) -> dict:
    return {
        "id": odoo_id,
        "name": f"Meta · 2026-11-wallbox-casa · {persona} · {comune}",
        "description": _html(fotovoltaico, auto, parcheggio, separatore),
        "phone": phone,
        "email_from": email if email else False,
        "city": city or comune,
        "stage_id": stage,
        "type": "opportunity",
        "user_id": user,
        "create_date": create_date,
        "active": active,
    }


# Istanti fissi, così i test possono congelare «adesso» al 24/11/2026 12:00 UTC.
LEADS_WALLBOX: list[dict] = [
    _lead(
        101,
        "Marta Conti",
        "Bologna",
        phone="+39 333 1112233",
        email="marta.conti@example.com",
        stage=[1, "New"],
        create_date="2026-11-24 08:00:00",
        fotovoltaico="sì",
        auto="sì",
        parcheggio="garage o box privato",
        user=[7, "Riccardo"],
    ),
    _lead(
        102,
        "Luca Ferri",
        "Napoli",
        phone="+39 347 5556677",
        email="luca.ferri@example.com",
        stage=[1, "New"],
        create_date="2026-11-20 12:00:00",
        fotovoltaico="no",
        auto="no",
        parcheggio="condominio",
        user=[7, "Riccardo"],
    ),
    _lead(
        103,
        "Elena Riva",
        "Como",
        phone="+393201112233",
        email="elena.riva@example.com",
        stage=[1, "New"],
        create_date="2026-11-22 12:00:00",
        fotovoltaico="no",
        auto="la prendo nei prossimi mesi",
        parcheggio="posto auto esterno privato",
        user=[7, "Riccardo"],
    ),
    _lead(
        104,
        "Paolo Neri",
        "Verona",
        phone="+39 340 9988776",
        email="paolo.neri@example.com",
        stage=[4, "Fissare Survey / Info"],
        create_date="2026-11-18 12:00:00",
        fotovoltaico="sì",
        auto="sì",
        parcheggio="garage o box privato",
        user=[8, "Marco"],
    ),
    _lead(
        105,
        "Chiara Gallo",
        "Parma",
        phone="+39 349 2223344",
        email="chiara.gallo@example.com",
        stage=[6, "Proposta Inviata"],
        create_date="2026-11-21 09:00:00",
        fotovoltaico="sì",
        auto="no",
        parcheggio="garage o box privato",
        user=[7, "Riccardo"],
    ),
    _lead(
        106,
        "Davide Serra",
        "Genova",
        phone="+39 366 7788990",
        email=None,
        stage=[7, "Negoziazione"],
        create_date="2026-11-19 15:30:00",
        fotovoltaico="no",
        auto="sì",
        parcheggio="posto auto esterno privato",
        user=[7, "Riccardo"],
    ),
    _lead(
        107,
        "Sara Leone",
        "Firenze",
        phone="+39 331 4455667",
        email="sara.leone@example.com",
        stage=[8, "Won"],
        create_date="2026-11-15 10:00:00",
        fotovoltaico="sì",
        auto="sì",
        parcheggio="garage o box privato",
        user=[7, "Riccardo"],
    ),
    _lead(
        108,
        "Giorgio Fontana",
        "Pisa",
        phone="+39 338 1010101",
        email="giorgio.fontana@example.com",
        stage=[1, "New"],
        create_date="2026-11-10 08:00:00",
        active=False,
        fotovoltaico="no",
        auto="no",
        parcheggio="condominio",
        user=[7, "Riccardo"],
    ),
    _lead(
        109,
        "Nina Greco",
        "Forlì",
        phone="+39 328 4455667",
        email="nina.greco@example.com",
        stage=[1, "New"],
        create_date="2026-11-23 18:45:00",
        fotovoltaico="no",
        auto="sì",
        parcheggio="garage o box privato",
        user=False,
        separatore="br",
    ),
]
