from datetime import datetime, timezone
from urllib.parse import unquote

import pytest

from tests.conftest import MARCO, RENATO, RICCARDO, login


@pytest.fixture
def fermo(monkeypatch):
    momento = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("mosaika.services.leads.adesso", lambda: momento)
    return momento


def test_home_e_health(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "width=device-width" in home.text
    assert "Lead wallbox" in home.text
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["app"] == "mosaika"
    assert body["odoo_source"] == "mock"
    assert body["odoo_allow_production"] is False
    assert body["prompt"] == "obiezioni_v1"
    assert "SEGRETO-ODOO-NON-DEVE-USCIRE" not in health.text
    assert client.get("/api/leads").status_code == 401


def test_lead_wallbox_nome_modulo_giorni(client, fermo):
    login(client, RICCARDO)
    elenco = client.get("/api/leads?filtro=tutti")
    assert elenco.status_code == 200
    dati = elenco.json()
    assert dati["riepilogo"]["totale"] == 9
    assert dati["riepilogo"]["da_chiamare"] == 4
    assert dati["riepilogo"]["giorni_piu_vecchio"] == 14

    scheda = client.get("/api/leads/101").json()
    assert scheda["nome"] == "Marta Conti"
    assert scheda["comune"] == "Bologna"
    assert scheda["create_date"] == "2026-11-24 08:00:00"
    assert scheda["giorni_attesa"] == 0
    assert scheda["in_ritardo"] is False
    assert scheda["stato"] == "da chiamare"
    assert scheda["modulo"]["fotovoltaico"]["valore"] == "sì"
    assert scheda["modulo"]["fotovoltaico"]["chiave"] == "hai il fotovoltaico?"
    assert scheda["modulo"]["auto"]["chiave"] == "hai un'auto elettrica o ibrida plug-in?"
    assert "_" not in scheda["modulo"]["parcheggio"]["chiave"]
    assert scheda["modulo"]["parcheggio"]["valore"] == "garage o box privato"
    assert scheda["versione_suggerita"] == "Solare"
    assert "ha il fotovoltaico" in scheda["etichette"]

    luca = client.get("/api/leads/102").json()
    assert luca["giorni_attesa"] == 4
    assert luca["in_ritardo"] is True
    assert luca["versione_suggerita"] == "Smart"
    assert "condominio" in luca["etichette"]

    elena = client.get("/api/leads/103").json()
    assert elena["giorni_attesa"] == 2
    assert elena["in_ritardo"] is False
    assert elena["modulo"]["auto"]["valore"] == "la prendo nei prossimi mesi"

    paolo = client.get("/api/leads/104").json()
    assert paolo["stato"] == "contattato"
    assert paolo["giorni_attesa"] == 6
    assert paolo["in_ritardo"] is False
    assert paolo["stage"] == "Fissare Survey / Info"

    assert client.get("/api/leads/105").json()["stato"] == "preventivo inviato"
    assert client.get("/api/leads/106").json()["stato"] == "preventivo inviato"
    assert client.get("/api/leads/106").json()["contatti"]["email"] is None
    assert client.get("/api/leads/107").json()["stato"] == "vinto"
    giorgio = client.get("/api/leads/108").json()
    assert giorgio["stato"] == "perso"
    assert giorgio["archiviato"] is True
    assert giorgio["giorni_attesa"] == 14
    nina = client.get("/api/leads/109").json()
    assert nina["comune"] == "Forlì"
    assert nina["assegnatario"] is None
    assert nina["modulo"]["fotovoltaico"]["valore"] == "no"


def test_filtri_e_ordine(client, fermo):
    login(client, RICCARDO)
    da_lavorare = client.get("/api/leads").json()
    assert da_lavorare["filtro"] == "da_lavorare"
    ids = [riga["odoo_lead_id"] for riga in da_lavorare["leads"]]
    assert ids == [101, 109, 103, 102, 105, 106, 104]
    assert da_lavorare["riepilogo"]["da_chiamare"] == 4

    chiamare = [riga["odoo_lead_id"] for riga in client.get("/api/leads?filtro=da_chiamare").json()["leads"]]
    assert chiamare == [101, 109, 103, 102]

    chiusi = {riga["odoo_lead_id"] for riga in client.get("/api/leads?filtro=chiusi").json()["leads"]}
    assert chiusi == {107, 108}

    patch = client.patch("/api/leads/102", json={"zona": "fuori zona"})
    assert patch.status_code == 200
    assert "fuori zona" in patch.json()["etichette"]
    ids = [riga["odoo_lead_id"] for riga in client.get("/api/leads").json()["leads"]]
    assert ids[-1] == 102
    assert ids == [101, 109, 103, 105, 106, 104, 102]


def test_stato_zona_qualifica_sopralluogo_visibili_a_tutti(client):
    login(client, RICCARDO)
    salvato = client.patch(
        "/api/leads/101",
        json={
            "zona": "in zona",
            "note": "Richiamare dopo le 18.",
            "versione": "Essenziale",
            "qualifica": {"auto_parcheggio": {"nota": "box doppio", "fatto": False}},
            "giro": {"contatore": True, "quadro": False},
        },
    )
    assert salvato.status_code == 200, salvato.text
    corpo = salvato.json()
    assert corpo["qualifica"]["auto_parcheggio"]["fatto"] is True
    assert corpo["qualifica"]["tempi"]["fatto"] is False
    assert corpo["giro"]["contatore"] is True
    assert corpo["giro"]["inverter"] is False
    assert corpo["versione"] == "Essenziale"
    assert corpo["aggiornato_da"] == "Riccardo"

    video = client.patch("/api/leads/103", json={"video_il": "2026-11-25T14:00:00Z"})
    assert video.status_code == 200
    assert video.json()["stato"] == "videochiamata fissata"
    assert video.json()["sopralluogo"] == "video"
    assert "sono Riccardo di BABOO" in video.json()["messaggi"]["video"]["testo"]
    assert "alle 15:00" in video.json()["messaggi"]["video"]["testo"]

    login(client, MARCO)
    visto = client.get("/api/leads/101").json()
    assert visto["note"] == "Richiamare dopo le 18."
    assert visto["zona"] == "in zona"
    assert visto["qualifica"]["auto_parcheggio"]["nota"] == "box doppio"
    assert visto["versione"] == "Essenziale"
    assert visto["giro"]["contatore"] is True

    foto = client.patch("/api/leads/102", json={"sopralluogo": "foto"})
    assert foto.json()["stato"] == "foto richieste"
    ricevute = client.patch("/api/leads/102", json={"foto_ricevute": True})
    assert ricevute.json()["stato"] == "preventivo da fare"
    assert ricevute.json()["foto_ricevute"] is True

    login(client, RENATO)
    assert client.get("/api/leads/101").json()["note"] == "Richiamare dopo le 18."
    assert client.get("/api/leads/102").json()["stato"] == "preventivo da fare"
    assert client.get("/api/leads/103").json()["stato"] == "videochiamata fissata"

    manuale = client.patch("/api/leads/109", json={"stato": "contattato"})
    assert manuale.json()["stato"] == "contattato"


def test_link_whatsapp(client):
    login(client, MARCO)
    scheda = client.get("/api/leads/101").json()
    assert scheda["contatti"]["tel"] == "tel:+393331112233"
    assert scheda["contatti"]["whatsapp"] == "https://wa.me/393331112233"
    assert scheda["contatti"]["email"] == "mailto:marta.conti@example.com"
    url = scheda["messaggi"]["foto"]["url"]
    assert url.startswith("https://wa.me/393331112233?text=")
    testo = unquote(url.split("?text=", 1)[1])
    assert testo == scheda["messaggi"]["foto"]["testo"]
    assert "sono Marco di BABOO" in testo
    assert "sono Riccardo" not in testo
    assert "Buongiorno Marta Conti" in testo

    elena = client.get("/api/leads/103").json()
    assert elena["contatti"]["whatsapp"] == "https://wa.me/393201112233"
    assert elena["messaggi"]["video"]["url"] is None


def test_aggiornamento_non_cancella_il_lavoro(client):
    login(client, RICCARDO)
    client.patch("/api/leads/101", json={"note": "Nota che resta."})
    aggiornato = client.post("/api/leads/aggiorna")
    assert aggiornato.status_code == 200
    assert client.get("/api/leads/101").json()["note"] == "Nota che resta."
    assert client.get("/api/leads/101").json()["nome"] == "Marta Conti"
