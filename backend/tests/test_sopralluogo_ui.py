"""Flusso di raccolta a 375 px. Parte se Playwright e Chromium sono installati."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright

BACKEND = Path(__file__).resolve().parents[1]
URL_DB = "postgresql+psycopg://mosaika:mosaika@localhost:5432/mosaika_sopra"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _porta_libera() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _attendi(url: str, proc: subprocess.Popen, log: Path) -> None:
    import urllib.request

    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(log.read_text(encoding="utf-8")[-4000:])
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(log.read_text(encoding="utf-8")[-4000:])


def _senza_scroll(page) -> None:
    larghezza = page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )
    assert larghezza, page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})"
    )


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import psycopg

    with psycopg.connect(
        "postgresql://mosaika:mosaika@localhost:5432/mosaika",
        autocommit=True,
    ) as conn:
        presente = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'mosaika_sopra'"
        ).fetchone()
        if not presente:
            conn.execute("CREATE DATABASE mosaika_sopra OWNER mosaika")
    with psycopg.connect(
        URL_DB.replace("postgresql+psycopg", "postgresql"),
        autocommit=True,
    ) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO mosaika")
        conn.execute("GRANT ALL ON SCHEMA public TO public")

    porta = _porta_libera()
    media = tmp_path_factory.mktemp("media")
    env = os.environ.copy()
    env.update(
        {
            "MOSAIKA_DATABASE_URL": URL_DB,
            "MOSAIKA_ODOO_SOURCE": "mock",
            "MOSAIKA_ODOO_ALLOW_PRODUCTION": "false",
            "MOSAIKA_AI_PROVIDER": "mock",
            "MOSAIKA_SEED_PASSWORD": "mosaika-dev",
            "MOSAIKA_SESSION_SECRET": "ui-sopra-secret",
            "MOSAIKA_PASSWORD_ITERATIONS": "2000",
            "MOSAIKA_SYNC_INTERVAL_SECONDS": "86400",
            "MOSAIKA_STORAGE_BACKEND": "local",
            "MOSAIKA_STORAGE_PATH": str(media),
            "PYTHONUNBUFFERED": "1",
        }
    )
    log_path = Path("/tmp/mosaika-sopra.log")
    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "mosaika.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(porta),
        ],
        cwd=BACKEND,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{porta}"
    try:
        _attendi(f"{base}/api/health", proc, log_path)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutError:
            proc.kill()
        log.close()


def test_raccolta_a_375(server, tmp_path):
    foto = tmp_path / "scatto.png"
    foto.write_bytes(PNG)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.goto(server + "/sopralluogo/")
        page.wait_for_selector("#login-form")
        _senza_scroll(page)
        page.fill('input[name="email"]', "marco@baboo.local")
        page.fill('input[name="password"]', "mosaika-dev")
        page.click('button[type="submit"]')
        page.wait_for_selector("[data-testid=elenco]")
        _senza_scroll(page)
        page.click("[data-testid=nuovo]")
        page.wait_for_selector("#form-nuovo")
        assert page.input_value("#opportunita") == "1733"
        assert "Bacchiglione" in page.input_value("#sito")
        _senza_scroll(page)
        page.click('#form-nuovo button[type="submit"]')
        page.wait_for_selector("[data-testid=rilievo]")
        _senza_scroll(page)
        assert page.locator("[data-testid=stato-sync]").inner_text()
        page.locator("[data-testid=sezione][data-codice=CT]").click()
        page.locator("[data-testid=voce]").first.wait_for()
        page.locator("[data-testid=voce]").first.click()
        page.wait_for_selector("[data-testid=scheda-voce]")
        assert "foto" in page.locator("[data-testid=mancanti]").inner_text()
        _senza_scroll(page)
        page.set_input_files("[data-testid=foto]", str(foto))
        page.wait_for_selector("[data-testid=nome-file]")
        assert "CT-01" in page.locator("[data-testid=nome-file]").first.inner_text()
        _senza_scroll(page)
        page.click("[data-testid=indietro]")
        page.locator("[data-testid=voce]", has_text="Dimensioni del locale").click()
        page.wait_for_selector("[data-testid=misura-valore]")
        page.fill("[data-testid=misura-valore]", "4.2")
        page.fill("[data-testid=misura-unita]", "m")
        page.click("[data-testid=salva-voce]")
        page.wait_for_function(
            "() => document.querySelector('[data-testid=misura-valore]')?.value === '4.2'"
        )
        _senza_scroll(page)
        page.click("[data-testid=indietro]")
        page.click("[data-testid=vai-chiusura]")
        page.wait_for_selector("[data-testid=chiusura]")
        assert "mancano" in page.locator("[data-testid=flag-temperature]").inner_text().lower()
        assert page.input_value("[data-testid=tecnico]") == "Marco"
        assert page.locator("[data-testid=firma]").is_visible()
        _senza_scroll(page)
        tema = page.evaluate("() => document.documentElement.dataset.theme")
        page.click("[data-testid=tema]")
        altro = page.evaluate("() => document.documentElement.dataset.theme")
        assert tema != altro
        assert {tema, altro} == {"light", "dark"}
        _senza_scroll(page)
        page.click("[data-testid=indietro]")
        page.locator("[data-testid=sezione][data-codice=CAN]").click()
        page.locator("[data-testid=voce]", has_text="Interviste ad amministratore").wait_for()
        page.locator("[data-testid=voce]", has_text="Interviste ad amministratore").click()
        page.wait_for_selector("[data-testid=consenso]")
        assert page.locator("[data-testid=registra-audio]").is_disabled()
        page.check("[data-testid=consenso]")
        assert page.locator("[data-testid=registra-audio]").is_enabled()
        _senza_scroll(page)
        browser.close()
