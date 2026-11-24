from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    """Radice del progetto, sia nel checkout sia nell'immagine Docker."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "prompts").is_dir() and (parent / "frontend").is_dir():
            return parent
    return here.parents[2]


REPO_ROOT = repo_root()


class Settings(BaseSettings):
    """Segreti e interruttori. Tutte le variabili d'ambiente hanno prefisso MOSAIKA_."""

    model_config = SettingsConfigDict(
        env_prefix="MOSAIKA_",
        env_file=str(REPO_ROOT / ".env"),
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://mosaika:mosaika@localhost:5432/mosaika"
    session_secret: str = "dev-session-secret-change-me"
    session_days: int = 14
    cookie_secure: bool = False

    # mock: fixture locali. xmlrpc: Odoo, solo se l'URL è l'istanza di test
    # oppure se MOSAIKA_ODOO_ALLOW_PRODUCTION è acceso (spento di default).
    odoo_source: str = "mock"
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""
    odoo_allow_production: bool = False
    odoo_test_marker: str = "esconnect18-test"

    # mock: nessuna rete, risponde solo con le risposte validate.
    # openai: endpoint compatibile con le API chat OpenAI.
    ai_provider: str = "mock"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"

    seed_password: str = "mosaika-dev"
    sync_interval_seconds: int = 600
    password_iterations: int = 120_000

    prompts_dir: str = ""
    frontend_dir: str = ""

    def prompts_path(self) -> Path:
        if self.prompts_dir:
            return Path(self.prompts_dir)
        return REPO_ROOT / "prompts"

    def frontend_path(self) -> Path:
        if self.frontend_dir:
            return Path(self.frontend_dir)
        return REPO_ROOT / "frontend"
