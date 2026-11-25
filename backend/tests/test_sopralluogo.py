import base64
import io
import json
import subprocess
import zipfile
from pathlib import Path

from mosaika.config import REPO_ROOT, Settings
from mosaika.sopralluogo.seed import seed_modelli
from mosaika.sopralluogo.storage import LocalStorage, S3Storage, build_storage

from tests.conftest import MARCO, RENATO, RICCARDO, login

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

MINI = """
codice: prova-mini
titolo: Prova mini
sito: Via Roma 1
revisione: "1"
sezioni:
  - codice: CT
    titolo: Centrale
    prefisso: CT
    tipo: raccolta
    voci:
      - testo: Targa caldaia
        evidenze: [F]
        capitolo: "3"
"""


def _voci(rilievo):
    for sezione in rilievo["sezioni"]:
        for voce in sezione["voci"]:
            yield sezione, voce


def _trova(rilievo, testo):
    for sezione, voce in _voci(rilievo):
        if testo in voce["testo"]:
            return sezione, voce
    raise AssertionError(testo)


def _apri(client, email=MARCO):
    login(client, email)
    response = client.post(
        "/api/sopralluogo/rilievi",
        json={
            "modello": "opp-1733",
            "sito": "Viale Bacchiglione 28, 20139 Milano",
            "odoo_opportunity_id": 1733,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _carica(client, rilievo_id, voce_id, nome, tipo, contenuto=b"foto", **campi):
    data = {"voce_id": str(voce_id), "tipo": tipo}
    data.update(campi)
    response = client.post(
        f"/api/sopralluogo/rilievi/{rilievo_id}/file",
        data=data,
        files={"file": (nome, contenuto, "image/png" if tipo == "F" else "application/octet-stream")},
    )
    return response


def test_modello_opp1733(client):
    login(client, MARCO)
    elenco = client.get("/api/sopralluogo/modelli")
    assert elenco.status_code == 200
    assert any(riga["codice"] == "opp-1733" for riga in elenco.json()["modelli"])
    modello = client.get("/api/sopralluogo/modelli/opp-1733").json()
    assert modello["odoo_opportunity_id"] == 1733
    assert "Bacchiglione" in modello["sito"]
    assert len(modello["sezioni"]) == 10
    voci = [voce for sezione in modello["sezioni"] for voce in sezione["voci"]]
    assert len(voci) == 73
    prefissi = {sezione["codice"]: sezione["prefisso"] for sezione in modello["sezioni"]}
    assert prefissi == {
        "PRE": "DOC",
        "STR": None,
        "CT": "CT",
        "IDR": "IDR",
        "PDC": "PDC",
        "EL": "EL",
        "RAD": "RAD",
        "TET": "TET",
        "CAN": "CAN",
        "FIN": None,
    }
    ubicazione = next(voce for voce in voci if voce["testo"].startswith("Ubicazione del locale"))
    assert ubicazione["evidenze"] == ["F", "V", "T"]
    assert ubicazione["capitolo"] == "3·4"
    dico = next(voce for voce in voci if voce["testo"].startswith("DiCo esistenti"))
    assert dico["evidenze"] == ["D"]
    assert dico["capitolo"] == "7"
    sottotetto = next(voce for voce in voci if voce["testo"].startswith("Sottotetto"))
    assert sottotetto["capitolo"] == "esclusa"
    temperature = next(voce for voce in voci if voce["chiave"] == "temperatura_mandata_ritorno")
    assert temperature["temperatura"] is True
    assert temperature["misure_minime"] == 2
    interviste = [voce for voce in voci if voce["consenso_richiesto"]]
    assert len(interviste) == 2
    assert all(voce["evidenze"] == ["A"] for voce in interviste)
    assert any(sezione["tipo"] == "strumenti" and len(sezione["voci"]) == 10 for sezione in modello["sezioni"])
    assert any(sezione["tipo"] == "chiusura" for sezione in modello["sezioni"])
    db = client.app.state.session_factory()
    try:
        seed_modelli(db)
        db.commit()
    finally:
        db.close()
    ancora = client.get("/api/sopralluogo/modelli").json()["modelli"]
    assert [riga["codice"] for riga in ancora].count("opp-1733") == 1


def test_import_e_ruoli(client):
    assert client.get("/api/sopralluogo/modelli").status_code == 401
    login(client, RICCARDO)
    assert client.get("/api/sopralluogo/modelli").status_code == 200
    negato = client.post("/api/sopralluogo/rilievi", json={"modello": "opp-1733"})
    assert negato.status_code == 403
    importa = client.post(
        "/api/sopralluogo/modelli",
        content=MINI.encode(),
        headers={"Content-Type": "application/yaml"},
    )
    assert importa.status_code == 403
    login(client, RENATO)
    creato = client.post(
        "/api/sopralluogo/modelli",
        content=MINI.encode(),
        headers={"Content-Type": "application/yaml"},
    )
    assert creato.status_code == 201, creato.text
    assert creato.json()["codice"] == "prova-mini"
    doppio = client.post(
        "/api/sopralluogo/modelli",
        content=MINI.encode(),
        headers={"Content-Type": "application/yaml"},
    )
    assert doppio.status_code == 409
    rilievo = _apri(client, RENATO)
    assert rilievo["odoo_opportunity_id"] == 1733
    assert rilievo["sito"].startswith("Viale Bacchiglione")


def test_upload_nome_metadati_e_consenso(client):
    rilievo = _apri(client)
    _, prima = _trova(rilievo, "Ubicazione del locale")
    _, seconda = _trova(rilievo, "Modulex 190")
    uno = _carica(
        client,
        rilievo["id"],
        prima["id"],
        "foto originale.jpg",
        "F",
        PNG,
        vista_insieme="true",
        gps_lat="45.44",
        gps_lon="9.21",
        gps_accuracy="8",
    )
    assert uno.status_code == 200, uno.text
    aggiornato = uno.json()
    _, voce = _trova(aggiornato, "Ubicazione del locale")
    assert voce["file"][0]["nome_assegnato"] == "CT-01.jpg"
    assert voce["file"][0]["nome_originale"] == "foto originale.jpg"
    assert voce["file"][0]["autore"] == "Marco"
    assert voce["file"][0]["vista_insieme"] is True
    assert abs(voce["file"][0]["gps"]["lat"] - 45.44) < 1e-6
    assert "F" not in voce["mancanti"]
    assert "V" in voce["mancanti"]
    due = _carica(client, rilievo["id"], seconda["id"], "targa.png", "F", PNG)
    assert due.status_code == 200, due.text
    _, modulex = _trova(due.json(), "Modulex 190")
    assert modulex["file"][0]["nome_assegnato"] == "CT-02.png"
    _, video = _trova(due.json(), "Video lento di tutta la centrale")
    solo_video = client.post(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/file",
        data={"voce_id": str(video["id"]), "tipo": "V"},
        files={"file": ("giro.webm", b"videobytes", "video/webm")},
    )
    assert solo_video.status_code == 200, solo_video.text
    _, video = _trova(solo_video.json(), "Video lento di tutta la centrale")
    assert video["mancanti"] == []
    _, intervista = _trova(solo_video.json(), "Interviste ad amministratore")
    senza = client.post(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/file",
        data={"voce_id": str(intervista["id"]), "tipo": "A", "consenso": "false"},
        files={"file": ("nota.webm", b"audio", "audio/webm")},
    )
    assert senza.status_code == 400
    assert "consenso" in senza.json()["detail"].lower()
    con = client.post(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/file",
        data={
            "voce_id": str(intervista["id"]),
            "tipo": "A",
            "consenso": "true",
            "consenso_nome": "Amministratore",
        },
        files={"file": ("intervista.webm", b"audio-ok", "audio/webm")},
    )
    assert con.status_code == 200, con.text
    _, intervista = _trova(con.json(), "Interviste ad amministratore")
    assert intervista["file"][0]["nome_assegnato"] == "CAN-01.webm"
    assert intervista["file"][0]["consenso"] is True
    assert intervista["file"][0]["consenso_nome"] == "Amministratore"
    scaricato = client.get(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/file/{intervista['file'][0]['id']}"
    )
    assert scaricato.status_code == 200
    assert scaricato.content == b"audio-ok"


def test_misure_e_non_applicabile(client):
    rilievo = _apri(client)
    _, dimensioni = _trova(rilievo, "Dimensioni del locale")
    assert "M" in dimensioni["mancanti"]
    salvate = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/voci/{dimensioni['id']}",
        json={"misure": [{"etichetta": "L", "valore": "4,2", "unita": "m"}], "stato": "fatto"},
    )
    assert salvate.status_code == 200, salvate.text
    _, dimensioni = _trova(salvate.json(), "Dimensioni del locale")
    assert dimensioni["misure"][0]["valore"] == "4.2"
    assert dimensioni["mancanti"] == []
    _, rumore = _trova(salvate.json(), "Rumore di fondo")
    una = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/voci/{rumore['id']}",
        json={"misure": [{"etichetta": "Diurno", "valore": "48", "unita": "dB(A)"}]},
    )
    assert "M" in _trova(una.json(), "Rumore di fondo")[1]["mancanti"]
    _, colonne = _trova(una.json(), "Numero colonne montanti")
    na = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/voci/{colonne['id']}",
        json={"stato": "non_applicabile"},
    )
    assert _trova(na.json(), "Numero colonne montanti")[1]["mancanti"] == []


def test_upload_a_pezzi(client):
    client.app.state.settings.upload_chunk_bytes = 4
    rilievo = _apri(client)
    _, voce = _trova(rilievo, "Modulex 190")
    sessione = client.post(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/upload",
        json={
            "voce_id": voce["id"],
            "tipo": "F",
            "nome_originale": "targa.png",
            "content_type": "image/png",
            "total_size": 10,
            "vista_insieme": True,
        },
    )
    assert sessione.status_code == 201, sessione.text
    corpo = sessione.json()
    assert corpo["nome_assegnato"] == "CT-01.png"
    assert corpo["parti"] == 3
    assert corpo["chunk_size"] == 4
    base = f"/api/sopralluogo/rilievi/{rilievo['id']}/upload/{corpo['id']}"
    assert client.put(f"{base}/parti/0", content=b"abcd").status_code == 200
    assert client.put(f"{base}/parti/0", content=b"ABCD").status_code == 200
    incompleto = client.post(f"{base}/completa")
    assert incompleto.status_code == 400
    assert client.put(f"{base}/parti/1", content=b"efgh").status_code == 200
    assert client.put(f"{base}/parti/2", content=b"ij").status_code == 200
    troppo = client.put(f"{base}/parti/2", content=b"troppo")
    assert troppo.status_code == 400
    fatto = client.post(f"{base}/completa")
    assert fatto.status_code == 200, fatto.text
    _, voce = _trova(fatto.json(), "Modulex 190")
    file_id = voce["file"][0]["id"]
    scaricato = client.get(f"/api/sopralluogo/rilievi/{rilievo['id']}/file/{file_id}")
    assert scaricato.content == b"ABCDefghij"
    di_nuovo = client.post(f"{base}/completa")
    assert di_nuovo.status_code == 200


def test_chiusura_temperature_e_firma(client):
    rilievo = _apri(client)
    _, temperature = _trova(rilievo, "Temperatura mandata e ritorno")
    assert rilievo["chiusura"]["temperature_complete"] is False
    assert rilievo["chiusura"]["senza_foto_insieme"]
    assert any(doc["testo"].startswith("Libretto") for doc in rilievo["chiusura"]["documenti_mancanti"])
    letture = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/voci/{temperature['id']}",
        json={
            "misure": [
                {
                    "etichetta": "Mandata",
                    "valore": "62",
                    "unita": "°C",
                    "rilevata_il": "2026-11-25T09:30:00",
                    "temperatura_esterna": "6",
                },
                {
                    "etichetta": "Ritorno",
                    "valore": "48",
                    "unita": "°C",
                    "rilevata_il": "2026-11-25T09:30:00",
                    "temperatura_esterna": "6",
                },
            ]
        },
    )
    assert letture.json()["chiusura"]["temperature_complete"] is True
    _, libretto = _trova(letture.json(), "Libretto di impianto")
    atteso = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/voci/{libretto['id']}",
        json={"chi_invia": "Amministratore", "entro_il": "2026-12-01"},
    )
    documenti = atteso.json()["chiusura"]["documenti_mancanti"]
    libretto_doc = next(doc for doc in documenti if doc["testo"].startswith("Libretto"))
    assert libretto_doc["chi_invia"] == "Amministratore"
    assert libretto_doc["entro_il"] == "2026-12-01"
    senza_firma = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/chiusura",
        json={"tecnico_nome": "Marco", "chiudi": True},
    )
    assert senza_firma.status_code == 400
    chiuso = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/chiusura",
        json={
            "tecnico_nome": "Marco Rossi",
            "firmato_il": "2026-11-25T18:05:00+01:00",
            "firma_png": base64.b64encode(PNG).decode(),
            "chiudi": True,
        },
    )
    assert chiuso.status_code == 200, chiuso.text
    corpo = chiuso.json()
    assert corpo["stato"] == "chiuso"
    assert corpo["tecnico_nome"] == "Marco Rossi"
    assert corpo["firma"] is True
    assert corpo["chiusura"]["firma"] is True


def test_export_zip(client):
    rilievo = _apri(client)
    _, foto = _trova(rilievo, "Ubicazione del locale")
    _, documento = _trova(rilievo, "Libretto di impianto")
    assert _carica(client, rilievo["id"], foto["id"], "IMG_100.jpg", "F", PNG, vista_insieme="true").status_code == 200
    doc = client.post(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/file",
        data={"voce_id": str(documento["id"]), "tipo": "D"},
        files={"file": ("libretto.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert doc.status_code == 200, doc.text
    firma = client.put(
        f"/api/sopralluogo/rilievi/{rilievo['id']}/chiusura",
        json={"tecnico_nome": "Marco", "firma_png": "data:image/png;base64," + base64.b64encode(PNG).decode()},
    )
    assert firma.status_code == 200, firma.text
    login(client, RICCARDO)
    export = client.get(f"/api/sopralluogo/rilievi/{rilievo['id']}/export")
    assert export.status_code == 200
    assert export.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(export.content)) as archivio:
        nomi = set(archivio.namelist())
        assert "riepilogo.json" in nomi
        assert "riepilogo.csv" in nomi
        assert "relazione.html" in nomi
        assert "chiusura/firma.png" in nomi
        assert "CT/CT-01.jpg" in nomi
        assert "CT/CT-01.jpg.json" in nomi
        assert "DOC/DOC-01.pdf" in nomi
        assert "DOC/DOC-01.pdf.json" in nomi
        sidecar = json.loads(archivio.read("CT/CT-01.jpg.json"))
        assert sidecar["nome_originale"] == "IMG_100.jpg"
        assert sidecar["autore"] == "Marco"
        assert sidecar["tipo"] == "F"
        assert archivio.read("CT/CT-01.jpg") == PNG
        html = archivio.read("relazione.html").decode("utf-8")
        assert "CAP. 3" in html
        assert "CAP. esclusa" in html
        assert "Ubicazione del locale" in html
        assert "Sottotetto" in html
        csv = archivio.read("riepilogo.csv").decode("utf-8-sig")
        assert ";" in csv.splitlines()[0]
        assert "IMG_100.jpg" in csv
        assert "CT-01.jpg" in csv
        riepilogo = json.loads(archivio.read("riepilogo.json"))
        assert riepilogo["odoo_opportunity_id"] == 1733
        assert "storage_key" not in json.dumps(riepilogo)


def test_coda_offline():
    script = Path(__file__).resolve().parent / "coda_offline.mjs"
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_storage_locale_e_s3(tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path / "locale")
    origine = tmp_path / "in.bin"
    origine.write_bytes(b"abc")
    storage.put_file("rilievi/1/CT/CT-01.bin", origine, "application/octet-stream")
    assert storage.open_path("rilievi/1/CT/CT-01.bin").read_bytes() == b"abc"
    try:
        storage.open_path("../segreto")
        raise AssertionError("path traversal")
    except ValueError:
        pass
    incompleto = Settings(
        _env_file=None,
        storage_backend="s3",
        s3_bucket="",
        s3_access_key="",
        s3_secret_key="",
        storage_path=str(tmp_path),
    )
    try:
        build_storage(incompleto)
        raise AssertionError("s3 senza parametri")
    except RuntimeError as exc:
        assert "S3" in str(exc)
    chiamate = {}

    class Client:
        def upload_file(self, *args, **kwargs):
            chiamate["upload"] = (args, kwargs)

    class Modulo:
        @staticmethod
        def client(nome, **kwargs):
            chiamate["kwargs"] = kwargs
            return Client()

    monkeypatch.setitem(__import__("sys").modules, "boto3", Modulo)
    impostazioni = Settings(
        _env_file=None,
        storage_backend="s3",
        storage_path=str(tmp_path / "stage"),
        s3_bucket="bucket",
        s3_access_key="ak",
        s3_secret_key="sk",
        s3_endpoint="http://minio.local:9000",
        s3_region="eu-south-1",
        s3_prefix="sopralluogo",
    )
    remoto = S3Storage(impostazioni)
    remoto.put_file("rilievi/1/CT/CT-01.bin", origine, "application/octet-stream")
    assert chiamate["kwargs"]["endpoint_url"] == "http://minio.local:9000"
    assert chiamate["kwargs"]["aws_access_key_id"] == "ak"
    assert chiamate["upload"][0][1] == "bucket"
    assert chiamate["upload"][0][2] == "sopralluogo/rilievi/1/CT/CT-01.bin"


def test_niente_odoo_e_niente_segreti(client):
    root = REPO_ROOT / "backend" / "mosaika" / "sopralluogo"
    for path in root.rglob("*.py"):
        testo = path.read_text(encoding="utf-8")
        assert "xmlrpc" not in testo
        assert "mosaika.odoo" not in testo
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["storage"] == "local"
    assert "sopralluogo" in health.json()["moduli"]
    assert "SEGRETO-S3-NON-DEVE-USCIRE" not in health.text
    html = (REPO_ROOT / "frontend" / "sopralluogo" / "index.html").read_text(encoding="utf-8")
    css = (REPO_ROOT / "frontend" / "css" / "app.css").read_text(encoding="utf-8")
    manifest = (REPO_ROOT / "frontend" / "sopralluogo" / "manifest.webmanifest").read_text(encoding="utf-8")
    assert 'lang="it"' in html
    assert "width=device-width" in html
    assert "Work+Sans" in html
    assert "JetBrains+Mono" in html
    assert "[data-theme=\"dark\"]" in css or '[data-theme="dark"]' in css
    assert '"display": "standalone"' in manifest
    assert "/sopralluogo/" in manifest


def test_shell_colori():
    css = (REPO_ROOT / "frontend" / "css" / "app.css").read_text(encoding="utf-8")
    for colore in ("#FFFFFF", "#374350", "#3C4348", "#5B6670", "#3F6A8A", "#EFF4F8", "#D6E1EA"):
        assert colore in css
