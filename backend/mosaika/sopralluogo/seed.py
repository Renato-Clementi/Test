"""Carica il modello OPP 1733 se non c'è già. Non riscrive un modello presente."""

from pathlib import Path

from mosaika.sopralluogo.models import ModelloChecklist
from mosaika.sopralluogo.servizio import _scrivi_modello
from mosaika.sopralluogo.template_io import carica_yaml

TEMPLATE_OPP1733 = Path(__file__).resolve().parent / "templates" / "opp1733.yaml"


def seed_modelli(db) -> None:
    if db.get(ModelloChecklist, "opp-1733") is not None:
        return
    _scrivi_modello(db, carica_yaml(TEMPLATE_OPP1733))
