"""Barriera di sola lettura verso Odoo.

La versione 1 non deve mai inviare un metodo che modifica i dati.
L'elenco qui sotto è ciò che il client può chiamare: qualunque altro
nome viene rifiutato prima ancora di aprire la rete.
"""


class OdooWriteForbidden(RuntimeError):
    pass


class OdooTargetForbidden(RuntimeError):
    pass


class OdooAuthError(RuntimeError):
    pass


READ_ONLY_METHODS = frozenset(
    {
        "search_read",
        "search",
        "read",
        "fields_get",
        "search_count",
        "name_get",
    }
)


def assert_read_only(method: str) -> None:
    if method not in READ_ONLY_METHODS:
        raise OdooWriteForbidden(
            f"Metodo Odoo non consentito in v1 (sola lettura): {method}"
        )


def assert_odoo_target_allowed(settings) -> None:
    """Il mock è sempre ammesso. XML-RPC solo verso esconnect18-test,
    a meno che l'interruttore di produzione sia acceso esplicitamente.
    """
    if settings.odoo_source != "xmlrpc":
        return
    url = settings.odoo_url or ""
    marker = settings.odoo_test_marker or "esconnect18-test"
    if marker in url:
        return
    if settings.odoo_allow_production:
        return
    raise OdooTargetForbidden(
        "In sviluppo Odoo può puntare solo all'istanza di test "
        f"«{marker}». La lettura della produzione resta spenta "
        "(MOSAIKA_ODOO_ALLOW_PRODUCTION) finché Renato non dà il consenso esplicito."
    )
