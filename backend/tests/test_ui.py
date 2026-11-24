"""Flusso nel browser: 375 px, desktop, tema chiaro e scuro.

Parte solo se Playwright e Chromium sono installati
(`pip install playwright && playwright install chromium`).
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright

from mosaika.services.assistente import FRASE_RINVIO

BACKEND = Path(__file__).resolve().parents[1]
URL_DB = "postgresql+psycopg://mosaika:mosaika@localhost:5432/mosaika_ui"


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
def server():
    import psycopg

    with psycopg.connect(
        "postgresql://mosaika:mosaika@localhost:5432/mosaika",
        autocommit=True,
    ) as conn:
        presente = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'mosaika_ui'"
        ).fetchone()
        if not presente:
            conn.execute("CREATE DATABASE mosaika_ui OWNER mosaika")
    with psycopg.connect(
        URL_DB.replace("postgresql+psycopg", "postgresql"),
        autocommit=True,
    ) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO mosaika")
        conn.execute("GRANT ALL ON SCHEMA public TO public")

    porta = _porta_libera()
    env = os.environ.copy()
    env.update(
        {
            "MOSAIKA_DATABASE_URL": URL_DB,
            "MOSAIKA_ODOO_SOURCE": "mock",
            "MOSAIKA_ODOO_ALLOW_PRODUCTION": "false",
            "MOSAIKA_AI_PROVIDER": "mock",
            "MOSAIKA_SEED_PASSWORD": "mosaika-dev",
            "MOSAIKA_SESSION_SECRET": "ui-test-secret",
            "MOSAIKA_PASSWORD_ITERATIONS": "2000",
            "MOSAIKA_SYNC_INTERVAL_SECONDS": "86400",
            "PYTHONUNBUFFERED": "1",
        }
    )
    log_path = Path("/tmp/mosaika-ui.log")
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


def test_telefono_desktop_e_tema(server):
    shots = Path("/tmp/mosaika-shot")
    shots.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.goto(server + "/")
        page.wait_for_selector("#login-form")
        page.fill('input[name="email"]', "riccardo@baboo.local")
        page.fill('input[name="password"]', "mosaika-dev")
        page.click('button[type="submit"]')
        page.wait_for_selector("[data-testid=elenco]")
        _senza_scroll(page)
        assert page.locator("[data-testid=lead-card]").count() >= 1
        page.screenshot(path=str(shots / "375-elenco-chiaro.png"), full_page=True)

        page.locator("[data-testid=lead-card]").first.click()
        page.wait_for_selector("[data-testid=scheda]")
        _senza_scroll(page)
        href = page.locator("[data-testid=wa-contatto]").get_attribute("href")
        assert href.startswith("https://wa.me/39")
        page.fill("[data-qualifica=auto_parcheggio]", "box doppio")
        assert page.locator("[data-fatto=auto_parcheggio]").is_checked()
        radio = page.locator('input[name="versione"]').first.bounding_box()
        assert radio["width"] < 32
        assert radio["height"] < 32
        assert page.locator("label.scelta", has_text="Videochiamata").inner_text().strip().endswith("Videochiamata")
        page.screenshot(path=str(shots / "375-scheda-chiaro.png"), full_page=True)

        tema = page.evaluate("() => document.documentElement.dataset.theme")
        page.click("[data-testid=tema]")
        altro = page.evaluate("() => document.documentElement.dataset.theme")
        assert tema != altro
        assert {tema, altro} == {"light", "dark"}
        page.screenshot(path=str(shots / "375-scheda-scuro.png"), full_page=True)

        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(100)
        _senza_scroll(page)
        page.screenshot(path=str(shots / "1280-scheda.png"), full_page=True)

        page.set_viewport_size({"width": 375, "height": 812})
        page.click('a[href="#/obiezioni"]')
        page.wait_for_selector("[data-testid=assistente]")
        page.fill("#domanda-assistente", "Si può installare in un condominio?")
        page.click("[data-testid=chiedi]")
        page.wait_for_selector("[data-testid=risposta-assistente]")
        assert FRASE_RINVIO in page.locator("[data-testid=risposta-assistente]").inner_text()
        _senza_scroll(page)
        page.screenshot(path=str(shots / "375-obiezioni.png"), full_page=True)

        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(100)
        _senza_scroll(page)
        browser.close()
