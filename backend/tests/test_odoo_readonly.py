import os
import re
from pathlib import Path

import pytest

from mosaika.config import REPO_ROOT, Settings
from mosaika.odoo.guard import (
    READ_ONLY_METHODS,
    OdooTargetForbidden,
    OdooWriteForbidden,
    assert_odoo_target_allowed,
    assert_read_only,
)
from mosaika.odoo.xmlrpc_source import (
    WALLBOX_CONTEXT,
    WALLBOX_DOMAIN,
    WALLBOX_FIELDS,
    WALLBOX_ORDER,
    OdooReadClient,
    XmlRpcOdooSource,
    build_odoo_source,
)
from mosaika.services.assistente import FRASE_RINVIO

METODI_VIETATI = (
    "create",
    "write",
    "unlink",
    "copy",
    "action_archive",
    "action_unarchive",
    "toggle_active",
    "message_post",
    "name_create",
)
PATTERN = re.compile(r"""['\"](%s)['\"]""" % "|".join(METODI_VIETATI))


def _settings(**kwargs):
    dati = dict(
        _env_file=None,
        database_url="postgresql+psycopg://mosaika:mosaika@localhost:5432/mosaika",
        session_secret="s",
        odoo_source="xmlrpc",
        odoo_url="https://esconnect18-test.example/odoo",
        odoo_db="odoo",
        odoo_username="lettore",
        odoo_password="segreto",
        odoo_allow_production=False,
    )
    dati.update(kwargs)
    return Settings(**dati)


class Registro:
    def __init__(self):
        self.calls = []

    def authenticate(self, db, username, password):
        self.calls.append(("authenticate", db, username))
        return 5

    def execute_kw(self, db, uid, password, model, method, args, kwargs):
        self.calls.append((method, model, args, kwargs))
        return []


def test_nessuna_scrittura_nel_codice():
    radici = [REPO_ROOT / "backend" / "mosaika", REPO_ROOT / "frontend"]
    colpi = []
    for radice in radici:
        for path in radice.rglob("*"):
            if path.suffix.lower() not in {".py", ".js", ".html", ".css"}:
                continue
            for numero, riga in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if PATTERN.search(riga):
                    colpi.append(f"{path}:{numero}: {riga.strip()}")
    assert colpi == []


def test_il_browser_non_chiama_odoo():
    frontend = REPO_ROOT / "frontend"
    for path in frontend.rglob("*"):
        if path.suffix.lower() not in {".js", ".html", ".css"}:
            continue
        testo = path.read_text(encoding="utf-8").lower()
        assert "xmlrpc" not in testo
        assert "execute_kw" not in testo


def test_client_rifiuta_i_metodi_di_scrittura_prima_della_rete():
    registro = Registro()
    client = OdooReadClient(_settings(), transport=registro)
    for metodo in ("create", "write", "unlink", "copy", "message_post"):
        with pytest.raises(OdooWriteForbidden):
            client.execute_kw("crm.lead", metodo, [[]], {})
    assert registro.calls == []
    for metodo in METODI_VIETATI:
        with pytest.raises(OdooWriteForbidden):
            assert_read_only(metodo)
    for metodo in READ_ONLY_METHODS:
        assert_read_only(metodo)


def test_la_lettura_wallbox_e_solo_search_read():
    registro = Registro()
    source = XmlRpcOdooSource(client=OdooReadClient(_settings(), transport=registro))
    assert source.search_read_wallbox_leads() == []
    assert [chiamata[0] for chiamata in registro.calls] == ["authenticate", "search_read"]
    metodo, model, args, kwargs = registro.calls[1]
    assert metodo == "search_read"
    assert model == "crm.lead"
    assert args == [WALLBOX_DOMAIN]
    assert kwargs["order"] == WALLBOX_ORDER
    assert kwargs["context"] == WALLBOX_CONTEXT
    assert kwargs["context"]["active_test"] is False
    for campo in (
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
    ):
        assert campo in kwargs["fields"]
    assert kwargs["fields"] == WALLBOX_FIELDS


def test_produzione_spenta_di_default(monkeypatch):
    for chiave in list(os.environ):
        if chiave.startswith("MOSAIKA_"):
            monkeypatch.delenv(chiave)
    settings = Settings(_env_file=None)
    assert settings.odoo_source == "mock"
    assert settings.odoo_allow_production is False
    assert_odoo_target_allowed(settings)


def test_xmlrpc_solo_verso_esconnect18_test():
    assert_odoo_target_allowed(_settings())
    with pytest.raises(OdooTargetForbidden):
        build_odoo_source(_settings(odoo_url="https://odoo-produzione.example"))
    consentita = _settings(
        odoo_url="https://odoo-produzione.example",
        odoo_allow_production=True,
    )
    assert_odoo_target_allowed(consentita)
    mock = _settings(odoo_source="mock", odoo_url="https://odoo-produzione.example")
    assert_odoo_target_allowed(mock)
    assert build_odoo_source(mock).__class__.__name__ == "MockOdooSource"


def test_prompt_contiene_la_frase_di_rinvio():
    testo = (REPO_ROOT / "prompts" / "obiezioni_v1.md").read_text(encoding="utf-8")
    assert FRASE_RINVIO in testo
    assert "obiezioni_v1" in testo


def test_niente_nomi_vietati():
    vietati = re.compile(r"fvteken|\bteken\b", re.IGNORECASE)
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(parte in {".git", ".venv", "__pycache__", "node_modules", "tests"} for parte in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".js", ".html", ".css", ".md", ".yml", ".yaml", ".txt", ".example", ".webmanifest", ".ini"}:
            continue
        if vietati.search(path.read_text(encoding="utf-8")):
            raise AssertionError(path)
