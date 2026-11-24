import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from mosaika.config import Settings
from mosaika.main import create_app

PASSWORD = "mosaika-dev"
CANARY = "SEGRETO-ODOO-NON-DEVE-USCIRE"


def _database_url() -> str:
    return os.environ.get(
        "MOSAIKA_TEST_DATABASE_URL",
        "postgresql+psycopg://mosaika:mosaika@localhost:5432/mosaika_test",
    )


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url=_database_url(),
        session_secret="test-secret",
        odoo_source="mock",
        odoo_allow_production=False,
        odoo_password=CANARY,
        ai_provider="mock",
        ai_api_key="",
        seed_password=PASSWORD,
        password_iterations=2_000,
        sync_interval_seconds=86_400,
    )


@pytest.fixture
def client(settings):
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO mosaika"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    engine.dispose()
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client


def login(client, email: str, password: str = PASSWORD):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


RICCARDO = "riccardo@baboo.local"
MARCO = "marco@baboo.local"
RENATO = "renato@baboo.local"
