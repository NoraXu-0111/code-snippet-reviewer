import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=3001, ge=1, le=65535)
    database_path: Path = PROJECT_ROOT / "data/reviewer.db"
    serve_client: bool = False
    openai_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    openai_model: str = "gpt-4.1-mini"
    review_timeout_seconds: float = Field(default=60, gt=0, le=300)


def get_settings() -> Settings:
    filename = os.getenv("DATABASE_PATH", "./data/reviewer.db")
    if filename.strip() in ("", ":memory:"):
        raise ValueError("A persistent SQLite file path is required")
    path = Path(filename)
    return Settings(
        host=os.getenv("HOST", "127.0.0.1"),
        port=os.getenv("PORT", "3001"),
        database_path=path if path.is_absolute() else PROJECT_ROOT / path,
        serve_client=os.getenv("SERVE_CLIENT", "false").lower() == "true",
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
        openai_model=os.getenv("OPENAI_MODEL", "").strip() or "gpt-4.1-mini",
        review_timeout_seconds=os.getenv("REVIEW_TIMEOUT_SECONDS", "60"),
    )
