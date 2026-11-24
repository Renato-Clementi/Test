import copy

from mosaika.odoo.fixtures import LEADS_WALLBOX


class MockOdooSource:
    """Fonte locale con gli stessi campi di `crm.lead`. Nessuna rete."""

    def __init__(self, leads: list | None = None):
        self._leads = LEADS_WALLBOX if leads is None else leads

    def search_read_wallbox_leads(self) -> list[dict]:
        return copy.deepcopy(self._leads)
