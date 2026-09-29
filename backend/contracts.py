from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)


class ReviewStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Resolution(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Category(StrEnum):
    BUG = "bug"
    STYLE = "style"
    PERFORMANCE = "performance"
    SECURITY = "security"


DashboardStatus = Literal["not_reviewed", "in_progress", "reviewed", "failed"]


class CreateSnippet(Contract):
    title: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=1, max_length=50)
    code: str = Field(min_length=1, max_length=100_000)

    @field_validator("title", "language", mode="before")
    @classmethod
    def trim_labels(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return value.lower()

    @field_validator("code")
    @classmethod
    def nonblank_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Code must contain non-whitespace characters")
        return value  # Do not alter whitespace or line endings.


class Snippet(CreateSnippet):
    id: UUID
    created_at: AwareDatetime


class ExecutionState(Contract):
    status: ReviewStatus
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    error: str | None = None

    @model_validator(mode="after")
    def valid_state_shape(self) -> Self:
        if self.status == ReviewStatus.QUEUED:
            valid = self.started_at is None and self.finished_at is None and self.error is None
        elif self.status == ReviewStatus.RUNNING:
            valid = self.started_at is not None and self.finished_at is None and self.error is None
        elif self.status == ReviewStatus.SUCCEEDED:
            valid = self.started_at is not None and self.finished_at is not None and self.error is None
        else:
            valid = self.finished_at is not None and bool(self.error and self.error.strip())
        if not valid:
            raise ValueError("Timestamps and error must match the execution status")
        return self


class ReviewRun(ExecutionState):
    id: UUID
    snippet_id: UUID


class CreateDiscussionTurn(Contract):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)
    client_request_id: UUID

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must contain non-whitespace characters")
        return value


class RetryDiscussionTurn(Contract):
    attempt: int = Field(strict=True, ge=1)


class DiscussionTurn(ExecutionState):
    conversation_id: UUID
    id: UUID
    finding_id: UUID
    client_request_id: UUID
    user_message: str = Field(min_length=1, max_length=4000)
    assistant_message: str | None = None
    attempt: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def valid_answer(self) -> Self:
        if self.status == ReviewStatus.SUCCEEDED:
            if not self.assistant_message or not self.assistant_message.strip():
                raise ValueError("Successful replies require an answer")
        elif self.assistant_message is not None:
            raise ValueError("Unsuccessful replies cannot contain an answer")
        return self


class DiscussionConversation(Contract):
    id: UUID
    finding_id: UUID
    created_at: AwareDatetime


class CreateConversation(Contract):
    client_request_id: UUID


class DiscussionDetail(Contract):
    conversation_id: UUID
    conversations: list[DiscussionConversation]
    has_active_reply: bool
    turns: list[DiscussionTurn]


class FindingContent(Contract):
    start_line: Annotated[int, Field(strict=True, ge=1)]
    end_line: Annotated[int, Field(strict=True, ge=1)]
    severity: Severity
    category: Category
    description: str = Field(min_length=1)
    suggested_fix: str | None = None

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def ordered_lines(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("endLine must be greater than or equal to startLine")
        return self


class Finding(FindingContent):
    id: UUID
    review_run_id: UUID
    resolution: Resolution = Resolution.OPEN


class ReviewOutput(Contract):
    findings: list[FindingContent]


def parse_review_output(value: object, code: str) -> ReviewOutput:
    output = ReviewOutput.model_validate(value)
    line_count = len(code.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    if any(finding.end_line > line_count for finding in output.findings):
        raise ValueError("Finding line reference exceeds snippet length")
    return output


def dashboard_status(status: ReviewStatus | None) -> DashboardStatus:
    if status is None:
        return "not_reviewed"
    if status in (ReviewStatus.QUEUED, ReviewStatus.RUNNING):
        return "in_progress"
    return "reviewed" if status == ReviewStatus.SUCCEEDED else "failed"


class HealthResponse(Contract):
    status: Literal["ok"] = "ok"
    database: Literal["connected"] = "connected"


class SnippetSummary(Contract):
    id: UUID
    title: str
    language: str
    created_at: AwareDatetime
    review_status: DashboardStatus


class SnippetList(Contract):
    snippets: list[SnippetSummary]
    languages: list[str]


class SnippetDetail(Contract):
    snippet: Snippet
    latest_review: ReviewRun | None


class ReviewHistory(Contract):
    reviews: list[ReviewRun]


class ReviewDetail(Contract):
    review: ReviewRun
    findings: list[Finding]


class UpdateFinding(Contract):
    resolution: Resolution


class ErrorBody(Contract):
    code: str
    message: str


class ErrorResponse(Contract):
    error: ErrorBody
