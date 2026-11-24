"""Client XML-RPC in sola lettura.

L'unico punto che parla con Odoo è `XmlRpcTransport`. Prima di ogni
chiamata al modello, `OdooReadClient` passa da `assert_read_only`.
"""

from __future__ import annotations

import xmlrpc.client

from mosaika.odoo.guard import (
    OdooAuthError,
    assert_odoo_target_allowed,
    assert_read_only,
)

WALLBOX_MODEL = "crm.lead"
WALLBOX_DOMAIN = [["campaign_id.name", "ilike", "Wallbox"]]
WALLBOX_FIELDS = [
    "name",
    "description",
    "phone",
    "email_from",
    "city",
    "stage_id",
    "type",
    "user_id",
    "create_date",
    "active",
]
WALLBOX_ORDER = "create_date desc"
# active_test falso: il brief chiede anche gli archiviati.
WALLBOX_CONTEXT = {"active_test": False}


class XmlRpcTransport:
    def __init__(self, url: str):
        base = url.rstrip("/")
        self.common = xmlrpc.client.ServerProxy(
            f"{base}/xmlrpc/2/common", allow_none=True
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{base}/xmlrpc/2/object", allow_none=True
        )

    def authenticate(self, db: str, username: str, password: str):
        return self.common.authenticate(db, username, password, {})

    def execute_kw(self, db, uid, password, model, method, args, kwargs):
        return self.models.execute_kw(db, uid, password, model, method, args, kwargs)


class OdooReadClient:
    def __init__(self, settings, transport=None):
        assert_odoo_target_allowed(settings)
        self.settings = settings
        self.transport = transport or XmlRpcTransport(settings.odoo_url)
        self._uid = None

    def execute_kw(self, model: str, method: str, args, kwargs):
        assert_read_only(method)
        uid = self._ensure_uid()
        return self.transport.execute_kw(
            self.settings.odoo_db,
            uid,
            self.settings.odoo_password,
            model,
            method,
            args,
            kwargs,
        )

    def _ensure_uid(self):
        if self._uid:
            return self._uid
        uid = self.transport.authenticate(
            self.settings.odoo_db,
            self.settings.odoo_username,
            self.settings.odoo_password,
        )
        if not uid:
            raise OdooAuthError("Autenticazione Odoo fallita")
        self._uid = uid
        return uid

    def search_read(self, model, domain, fields, order, context):
        return self.execute_kw(
            model,
            "search_read",
            [domain],
            {"fields": fields, "order": order, "context": context},
        )


class XmlRpcOdooSource:
    def __init__(self, settings=None, client: OdooReadClient | None = None):
        if client is None:
            if settings is None:
                raise RuntimeError("Manca la configurazione Odoo")
            client = OdooReadClient(settings)
        self.client = client

    def search_read_wallbox_leads(self) -> list:
        return self.client.search_read(
            WALLBOX_MODEL,
            WALLBOX_DOMAIN,
            WALLBOX_FIELDS,
            WALLBOX_ORDER,
            WALLBOX_CONTEXT,
        )


def build_odoo_source(settings):
    if settings.odoo_source == "mock":
        from mosaika.odoo.mock_source import MockOdooSource

        return MockOdooSource()
    if settings.odoo_source == "xmlrpc":
        assert_odoo_target_allowed(settings)
        return XmlRpcOdooSource(settings)
    raise RuntimeError(
        f"MOSAIKA_ODOO_SOURCE non riconosciuta: {settings.odoo_source}. "
        "Valori ammessi: mock, xmlrpc."
    )
