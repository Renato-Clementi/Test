from datetime import datetime, timezone

from mosaika.odoo.fixtures import LEADS_WALLBOX
from mosaika.odoo.parser import (
    etichetta_campo,
    giorni_attesa,
    parse_descrizione,
    parse_nome_comune,
    stato_da_odoo,
    versione_suggerita,
)
from mosaika.services.leads import in_ritardo
from mosaika.services.whatsapp import messaggio_foto, messaggio_video, numero_wa, wa_link


def test_nome_e_comune():
    nome, comune = parse_nome_comune(
        "Meta · 2026-11-wallbox-casa · Giulia Bianchi · Reggio Emilia"
    )
    assert nome == "Giulia Bianchi"
    assert comune == "Reggio Emilia"


def test_descrizione_html_e_chiavi_leggibili():
    html = (
        "<div>"
        "<p><b>hai_il_fotovoltaico?:</b> sì</p>"
        "<p><b>hai_un'auto_elettrica_o_ibrida_plug-in?:</b> "
        "la prendo nei prossimi mesi</p>"
        "<p><b>dove_parcheggi_l'auto?:</b> condominio</p>"
        "</div>"
    )
    modulo = parse_descrizione(html)
    assert modulo == {
        "fotovoltaico": "sì",
        "auto": "la prendo nei prossimi mesi",
        "parcheggio": "condominio",
    }
    assert etichetta_campo("fotovoltaico") == "hai il fotovoltaico?"
    assert etichetta_campo("auto") == "hai un'auto elettrica o ibrida plug-in?"
    assert etichetta_campo("parcheggio") == "dove parcheggi l'auto?"
    assert "_" not in etichetta_campo("fotovoltaico")


def test_descrizione_con_a_capo():
    html = (
        "<b>hai_il_fotovoltaico?:</b> no<br>"
        "<b>hai_un'auto_elettrica_o_ibrida_plug-in?:</b> sì<br>"
        "<b>dove_parcheggi_l'auto?:</b> posto auto esterno privato"
    )
    modulo = parse_descrizione(html)
    assert modulo["fotovoltaico"] == "no"
    assert modulo["auto"] == "sì"
    assert modulo["parcheggio"] == "posto auto esterno privato"


def test_stato_derivato_da_odoo():
    assert stato_da_odoo(False, "Won") == "perso"
    assert stato_da_odoo(False, "New") == "perso"
    assert stato_da_odoo(True, "Won") == "vinto"
    assert stato_da_odoo(True, "Proposta Inviata") == "preventivo inviato"
    assert stato_da_odoo(True, "Negoziazione") == "preventivo inviato"
    assert stato_da_odoo(True, "Fissare Survey / Info") == "contattato"
    assert stato_da_odoo(True, "New") == "da chiamare"
    assert stato_da_odoo(True, "") == "da chiamare"


def test_giorni_e_ritardo():
    adesso = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
    assert giorni_attesa(datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc), adesso) == 4
    assert giorni_attesa(datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc), adesso) == 2
    assert giorni_attesa(datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc), adesso) == 0
    assert in_ritardo(3, "da chiamare") is True
    assert in_ritardo(2, "da chiamare") is False
    assert in_ritardo(6, "contattato") is False


def test_versione_suggerita():
    assert versione_suggerita("sì") == "Solare"
    assert versione_suggerita("Si") == "Solare"
    assert versione_suggerita("no") == "Smart"
    assert versione_suggerita(None) == "Smart"


def test_fixture_nel_formato_del_brief():
    assert len(LEADS_WALLBOX) >= 8
    for lead in LEADS_WALLBOX:
        assert lead["name"].startswith("Meta · 2026-11-wallbox-casa · ")
        assert lead["name"].count("·") == 3
        assert lead["phone"].startswith("+39")
        assert len(lead["create_date"]) == 19
        datetime.strptime(lead["create_date"], "%Y-%m-%d %H:%M:%S")
        modulo = parse_descrizione(lead["description"])
        assert modulo["fotovoltaico"] in {"sì", "no"}
        assert modulo["parcheggio"]
        nome, comune = parse_nome_comune(lead["name"], lead["city"])
        assert nome
        assert comune


def test_whatsapp_prefisso_e_mittente():
    assert numero_wa("+39 333 1112233") == "393331112233"
    assert numero_wa("+393201112233") == "393201112233"
    assert wa_link("+39 333 1112233") == "https://wa.me/393331112233"
    testo = messaggio_foto("Marta Conti", "Marco")
    assert testo.startswith("Buongiorno Marta Conti, sono Marco di BABOO.")
    assert "sono Riccardo" not in testo
    assert "1. il contatore" in testo
    assert "2. il quadro elettrico, aperto;" in testo
    assert "3. il punto dove vorrebbe la wallbox;" in testo
    assert "4. il percorso dal quadro al posto auto" in testo
    assert "5. se c'è, l'inverter del fotovoltaico." in testo
    video = messaggio_video("Marta Conti", "Riccardo", "mercoledì 25 novembre alle 15:00")
    assert "sono Riccardo di BABOO" in video
    assert "mercoledì 25 novembre alle 15:00" in video
