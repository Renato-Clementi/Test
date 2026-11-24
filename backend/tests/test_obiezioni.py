from mosaika.services.assistente import FRASE_RINVIO
from tests.conftest import MARCO, RENATO, RICCARDO, login


class ProviderPrezzo:
    name = "falso"

    def __init__(self):
        self.chiamate = 0

    def complete(self, *, system, user):
        self.chiamate += 1
        return "Costa 1.500 € e l'incentivo è del 50%."


def test_seed_placeholder_in_bozza(client):
    login(client, RICCARDO)
    righe = client.get("/api/obiezioni").json()["obiezioni"]
    assert len(righe) == 7
    assert [riga["validata"] for riga in righe] == [False] * 7
    assert {riga["badge"] for riga in righe} == {"in bozza"}
    for indice, riga in enumerate(reversed(righe), start=1):
        assert f"PLACEHOLDER {indice}/7" in riga["domanda"]
        assert "BOZZA" in riga["risposta"]
        assert "claude.ai" in riga["risposta"]


def test_solo_tecnico_e_admin_validano(client):
    login(client, RICCARDO)
    righe = client.get("/api/obiezioni").json()["obiezioni"]
    obiettivo = righe[0]["id"]
    negato = client.patch(
        f"/api/obiezioni/{obiettivo}",
        json={"risposta": "Una risposta del commerciale.", "validata": True},
    )
    assert negato.status_code == 403
    ancora = client.get("/api/obiezioni").json()["obiezioni"]
    originale = next(riga for riga in ancora if riga["id"] == obiettivo)
    assert originale["validata"] is False
    assert "commerciale" not in originale["risposta"]

    creata = client.post(
        "/api/obiezioni",
        json={"domanda": "Ma il contatore regge?", "risposta": "no", "validata": True},
    )
    assert creata.status_code == 403
    nuova = client.post(
        "/api/obiezioni",
        json={"domanda": "Ma il contatore regge?", "comune": "Bologna"},
    )
    assert nuova.status_code == 200
    assert nuova.json()["validata"] is False
    assert nuova.json()["badge"] == "senza risposta"
    assert nuova.json()["comune"] == "Bologna"

    login(client, MARCO)
    validata = client.patch(
        f"/api/obiezioni/{obiettivo}",
        json={
            "risposta": (
                "Sì, in condominio serve la delibera dell'assemblea. "
                "Il cavo resta in canalina."
            ),
            "validata": True,
        },
    )
    assert validata.status_code == 200, validata.text
    assert validata.json()["validata"] is True
    assert validata.json()["badge"] == "validata"
    assert validata.json()["validata_da"] == "Marco"

    login(client, RENATO)
    altra = client.post(
        "/api/obiezioni",
        json={
            "domanda": "Serve un permesso del comune?",
            "risposta": "Dipende dal regolamento comunale, lo verifica il tecnico.",
            "validata": True,
            "comune": "Como",
        },
    )
    assert altra.status_code == 200
    assert altra.json()["validata_da"] == "Renato"

    prima = client.get("/api/obiezioni").json()["obiezioni"]
    assert prima[0]["validata"] is True
    assert prima[1]["validata"] is True


def test_assistente_rinvia_senza_risposte_validate(client):
    login(client, RICCARDO)
    prima = len(client.get("/api/obiezioni").json()["obiezioni"])
    provider = client.app.state.ai_provider
    risposta = client.post(
        "/api/assistente",
        json={"domanda": "Si può installare in un condominio?"},
    )
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["risposta"] == FRASE_RINVIO
    assert corpo["fallback"] is True
    assert corpo["fonti"] == []
    assert corpo["provider"] == "nessuno"
    assert provider.chiamate == 0
    assert len(client.get("/api/obiezioni").json()["obiezioni"]) == prima

    prezzo = client.post(
        "/api/assistente",
        json={"domanda": "Qual è il prezzo chiavi in mano e quale incentivo posso avere?"},
    )
    assert prezzo.json()["risposta"] == FRASE_RINVIO


def test_assistente_usa_solo_le_validate_e_scarta_i_prezzi(client):
    login(client, MARCO)
    creata = client.post(
        "/api/obiezioni",
        json={
            "domanda": "Si può installare in condominio con il consenso dell'assemblea?",
            "risposta": (
                "Sì, in condominio serve la delibera dell'assemblea. "
                "Il cavo resta in canalina."
            ),
            "validata": True,
        },
    )
    assert creata.status_code == 200
    login(client, RICCARDO)
    provider = client.app.state.ai_provider
    risposta = client.post(
        "/api/assistente",
        json={"domanda": "In condominio serve l'assemblea per la wallbox?"},
    )
    corpo = risposta.json()
    assert corpo["fallback"] is False
    assert creata.json()["id"] in corpo["fonti"]
    assert "delibera dell'assemblea" in corpo["risposta"]
    assert "PLACEHOLDER" not in provider.ultimo_user
    assert "PLACEHOLDER" not in provider.ultimo_system
    assert "[VALIDATA]" in provider.ultimo_user
    assert FRASE_RINVIO in provider.ultimo_system
    assert provider.chiamate == 1

    falso = ProviderPrezzo()
    client.app.state.ai_provider = falso
    filtrata = client.post(
        "/api/assistente",
        json={"domanda": "In condominio serve l'assemblea per la wallbox?"},
    )
    assert falso.chiamate == 1
    assert "€" not in filtrata.json()["risposta"]
    assert "50%" not in filtrata.json()["risposta"]
    assert "delibera dell'assemblea" in filtrata.json()["risposta"]
    assert filtrata.json()["fallback"] is False
