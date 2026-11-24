import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mosaika.config import Settings
from mosaika.database import Base, make_engine, make_session_factory
from mosaika.odoo.xmlrpc_source import build_odoo_source
from mosaika.ai.provider import build_provider
from mosaika.routers.assistente import router as assistente_router
from mosaika.routers.auth import router as auth_router
from mosaika.routers.leads import router as leads_router
from mosaika.routers.obiezioni import router as obiezioni_router
from mosaika.seed import seed
from mosaika.services.sync import sincronizza_lead
from mosaika.timeutil import adesso

log = logging.getLogger("mosaika")


def create_app(
    settings: Settings | None = None,
    source=None,
    provider=None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(app.state.engine)
        db = app.state.session_factory()
        try:
            seed(db, app.state.settings)
            try:
                app.state.sync_count = sincronizza_lead(db, app.state.odoo_source)
                app.state.last_sync = adesso()
                app.state.sync_error = None
            except Exception as exc:
                log.exception("Lettura iniziale della fonte non riuscita")
                app.state.sync_error = str(exc)
        finally:
            db.close()

        stop = asyncio.Event()

        async def ciclo():
            while True:
                try:
                    await asyncio.wait_for(
                        stop.wait(),
                        timeout=app.state.settings.sync_interval_seconds,
                    )
                    return
                except asyncio.TimeoutError:
                    db_ciclo = app.state.session_factory()
                    try:
                        app.state.sync_count = sincronizza_lead(
                            db_ciclo, app.state.odoo_source
                        )
                        app.state.last_sync = adesso()
                        app.state.sync_error = None
                    except Exception as exc:
                        log.exception("Lettura periodica della fonte non riuscita")
                        app.state.sync_error = str(exc)
                    finally:
                        db_ciclo.close()

        task = asyncio.create_task(ciclo())
        try:
            yield
        finally:
            stop.set()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            app.state.engine.dispose()

    app = FastAPI(title="MOSAIKA Lead wallbox", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.odoo_source = source if source is not None else build_odoo_source(settings)
    app.state.ai_provider = provider if provider is not None else build_provider(settings)
    app.state.sync_error = None
    app.state.last_sync = None
    app.state.sync_count = 0

    @app.get("/api/health")
    def health(request: Request):
        config = request.app.state.settings
        ultimo = request.app.state.last_sync
        return {
            "app": "mosaika",
            "modulo": "lead-wallbox",
            "odoo_source": config.odoo_source,
            "odoo_allow_production": bool(config.odoo_allow_production),
            "ai_provider": config.ai_provider,
            "prompt": "obiezioni_v1",
            "ultimo_sync": ultimo.isoformat() if ultimo else None,
            "sync_error": request.app.state.sync_error,
        }

    app.include_router(auth_router, prefix="/api")
    app.include_router(leads_router, prefix="/api")
    app.include_router(obiezioni_router, prefix="/api")
    app.include_router(assistente_router, prefix="/api")

    frontend = settings.frontend_path()
    if not frontend.is_dir():
        raise RuntimeError(f"Frontend non trovato: {frontend}")

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(
            frontend / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
