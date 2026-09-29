import asyncio
from contextlib import asynccontextmanager, closing
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import PROJECT_ROOT, Settings, get_settings
from .contracts import CreateReview, CreateSnippet, DashboardStatus, ErrorResponse, Finding, HealthResponse, ReviewDetail, ReviewRun, Snippet, SnippetDetail, SnippetList, UpdateFinding
from .contracts import CreateConversation, DiscussionConversation, CreateDiscussionTurn, DiscussionDetail, DiscussionTurn, RetryDiscussionTurn, ReviewHistory
from .database import open_database
from .tracing import recover_traces
from . import findings, snippets
from .quality import quality_router
from .reviewer import OpenAIReviewer, Reviewer
from .reviews import ActiveReviewError, ReviewNotConfigured, ReviewService, get_review
from .discussion_provider import DiscussionProvider, OpenAIDiscussionProvider
from .discussions import DiscussionConflict, DiscussionNotConfigured, DiscussionService, get_discussion, create_conversation


def create_app(settings: Settings | None = None, *, reviewer: Reviewer | None = None,
               discussion_provider: DiscussionProvider | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        open_database(settings.database_path).close()
        slots = asyncio.Semaphore(2)
        service = ReviewService(settings.database_path, reviewer or OpenAIReviewer(settings), settings.review_timeout_seconds, slots,
                                configured=reviewer is not None or bool(settings.openai_api_key))
        discussions = DiscussionService(settings.database_path, discussion_provider or OpenAIDiscussionProvider(settings),
                                        settings.review_timeout_seconds, slots,
                                        configured=discussion_provider is not None or bool(settings.openai_api_key))
        recover_traces(settings.database_path)
        service.recover_interrupted()
        discussions.recover_interrupted()
        app.state.reviews = service
        app.state.discussions = discussions
        try:
            yield
        finally:
            await asyncio.gather(service.close(), discussions.close())

    app = FastAPI(title="Code Snippet Reviewer", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(DiscussionConflict)
    async def discussion_conflict(request: Request, exc: DiscussionConflict):
        return JSONResponse(status_code=409, content={"error": {"code": "discussion_conflict", "message": str(exc)}})

    @app.exception_handler(DiscussionNotConfigured)
    async def discussion_not_configured(request: Request, exc: DiscussionNotConfigured):
        return JSONResponse(status_code=503, content={"error": {"code": "not_configured", "message": "Set OPENAI_API_KEY in .env and restart the API to enable discussion."}})

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

    @app.get("/api/snippets/{snippet_id}/reviews", response_model=ReviewHistory,
             responses={404: {"model": ErrorResponse}})
    def review_history(snippet_id: UUID) -> ReviewHistory:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            if db.execute("SELECT 1 FROM snippets WHERE id = ?", (str(snippet_id),)).fetchone() is None:
                raise HTTPException(404, "Snippet not found")
            rows = db.execute("SELECT * FROM review_runs WHERE snippet_id = ? ORDER BY created_at DESC, rowid DESC", (str(snippet_id),))
            return ReviewHistory(reviews=[ReviewRun.model_validate(dict(row)) for row in rows])

    @app.post("/api/snippets/{snippet_id}/reviews", response_model=ReviewRun, status_code=202,
              responses={200: {"model": ReviewRun}, 400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
    async def start_review(snippet_id: UUID, payload: CreateReview, response: Response) -> ReviewRun:
        try:
            run, created = app.state.reviews.submit(snippet_id, payload.client_request_id)
            response.status_code = 202 if created else 200
            return run
        except ReviewNotConfigured:
            raise HTTPException(503, "Set OPENAI_API_KEY in .env and restart the API to enable reviews.") from None
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

    @app.patch("/api/findings/{finding_id}", response_model=Finding,
               responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
    def update_finding(finding_id: UUID, payload: UpdateFinding) -> Finding:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            result = findings.update_resolution(db, finding_id, payload.resolution)
        if result is None:
            raise HTTPException(404, "Finding not found")
        return result

    @app.get("/api/findings/{finding_id}/discussion", response_model=DiscussionDetail,
             responses={404: {"model": ErrorResponse}})
    def discussion_detail(finding_id: UUID, conversation_id: Annotated[UUID | None, Query(alias="conversationId")] = None) -> DiscussionDetail:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            try:
                return get_discussion(db, finding_id, conversation_id)
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from None

    @app.post("/api/findings/{finding_id}/conversations", response_model=DiscussionConversation, status_code=201,
              responses={200: {"model": DiscussionConversation}, 400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def new_conversation(finding_id: UUID, payload: CreateConversation, response: Response) -> DiscussionConversation:
        with closing(open_database(settings.database_path, migrate=False)) as db:
            try:
                conversation, created = create_conversation(db, finding_id, payload.client_request_id)
                response.status_code = 201 if created else 200
                return conversation
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from None

    @app.post("/api/findings/{finding_id}/discussion", response_model=DiscussionTurn, status_code=202,
              responses={200: {"model": DiscussionTurn}, 400: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                         409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
    async def start_discussion(finding_id: UUID, payload: CreateDiscussionTurn, response: Response) -> DiscussionTurn:
        try:
            turn, created = app.state.discussions.submit(finding_id, payload)
            response.status_code = 202 if created else 200
            return turn
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.post("/api/discussion-turns/{turn_id}/retry", response_model=DiscussionTurn, status_code=202,
              responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                         409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
    async def retry_discussion(turn_id: UUID, payload: RetryDiscussionTurn) -> DiscussionTurn:
        try:
            return app.state.discussions.retry(turn_id, payload.attempt)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None

    app.include_router(quality_router(settings))

    if settings.serve_client:
        app.mount("/", StaticFiles(directory=PROJECT_ROOT / "dist/client", html=True), name="client")
    return app


app = create_app()
