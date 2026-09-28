from contextlib import asynccontextmanager, closing

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT, Settings, get_settings
from .contracts import HealthResponse
from .database import open_database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        open_database(settings.database_path).close()
        yield

    app = FastAPI(title="Code Snippet Reviewer", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        # Each request owns its connection; no shared connection crosses threads.
        with closing(open_database(settings.database_path, migrate=False)) as db:
            db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        return HealthResponse()

    if settings.serve_client:
        app.mount("/", StaticFiles(directory=PROJECT_ROOT / "dist/client", html=True), name="client")
    return app


app = create_app()
