from contextlib import asynccontextmanager, closing
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import PROJECT_ROOT, Settings, get_settings
from .contracts import CreateSnippet, DashboardStatus, ErrorResponse, HealthResponse, ReviewDetail, ReviewRun, Snippet, SnippetDetail, SnippetList
from .database import open_database
from . import snippets
from .reviewer import OpenAIReviewer, Reviewer
from .reviews import ActiveReviewError, ReviewService, get_review


def create_app(settings: Settings | None = None, *, reviewer: Reviewer | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        open_database(settings.database_path).close()
        service = ReviewService(settings.database_path, reviewer or OpenAIReviewer(settings), settings.review_timeout_seconds)
        service.recover_interrupted()
        app.state.reviews = service
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="Code Snippet Reviewer", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        error = exc.errors()[0]
        field = ".".join(str(part) for part in error["loc"] if part not in ("body", "query", "path"))
        message = f"{field}: {error['msg']}" if field else error["msg"]
        return JSONResponse(status_code=400, content={"error": {"code": "validation_error", "message": message}})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 409: "review_in_progress", 503: "not_configured"}.get(exc.status_code, "request_error")
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": str(exc.detail)}})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        import logging
        logging.getLogger(__name__).exception("Unhandled request failure", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Something went wrong. Please try again."}})

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        # Each request owns its connection; no shared connection crosses threads.
        with closing(open_database(settings.database_path, migrate=False)) as db:
            db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        return HealthResponse()

    @app.post("/api/snippets", response_model=Snippet, status_code=201, responses={400: {"model": ErrorResponse}})
    def create_snippet(payload: CreateSnippet) -> Snippet:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            return snippets.create_snippet(db, payload)

    @app.get("/api/snippets", response_model=SnippetList, responses={400: {"model": ErrorResponse}})
    def list_snippets(
        language: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        review_status: Annotated[DashboardStatus | None, Query(alias="reviewStatus")] = None,
    ) -> SnippetList:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            return snippets.list_snippets(db, language.strip().lower() if language else None, review_status)

    @app.get("/api/snippets/{snippet_id}", response_model=SnippetDetail, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
    def get_snippet(snippet_id: UUID) -> SnippetDetail:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            result = snippets.get_snippet(db, snippet_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Snippet not found")
        return result

    @app.post("/api/snippets/{snippet_id}/reviews", response_model=ReviewRun, status_code=202,
              responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
    async def start_review(snippet_id: UUID) -> ReviewRun:
        if reviewer is None and not settings.openai_api_key:
            raise HTTPException(503, "Set OPENAI_API_KEY in .env and restart the API to enable reviews.")
        try:
            return app.state.reviews.submit(snippet_id)
        except LookupError:
            raise HTTPException(404, "Snippet not found") from None
        except ActiveReviewError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/reviews/{review_id}", response_model=ReviewDetail, responses={404: {"model": ErrorResponse}})
    def review_detail(review_id: UUID) -> ReviewDetail:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            result = get_review(db, review_id)
        if result is None:
            raise HTTPException(404, "Review not found")
        return result

    if settings.serve_client:
        app.mount("/", StaticFiles(directory=PROJECT_ROOT / "dist/client", html=True), name="client")
    return app


app = create_app()
