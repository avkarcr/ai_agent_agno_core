"""Configuration and watched source validation."""
from pathlib import Path
import json
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORE_", env_file=".env", extra="ignore")
    db_path: Path = Path(".local/core.sqlite3")
    watches_file: Path = Path("watchers.json")
    poll_minutes: int = Field(default=30, ge=1)
    analyze_changes: bool = False
    model_provider: Literal["ollama", "openai"] = "ollama"
    ollama_model: str = "qwen2.5:3b"
    ollama_host: str = "http://127.0.0.1:11434"
    openai_model: str = "gpt-5-mini"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class Watch(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=150)
    kind: Literal["rss", "json"]
    url: HttpUrl
    json_path: str | None = None
    min_delta: float = Field(default=0.0, ge=0.0)
    max_items: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_source(self):
        if self.kind == "json" and not self.json_path:
            raise ValueError("json watches require json_path")
        return self


def load_watches(path: Path) -> list[Watch]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}. Copy watchers.example.json to watchers.json")
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Watches configuration must be an array")
    watches = [Watch.model_validate(item) for item in items]
    ids = [watch.id for watch in watches]
    if len(ids) != len(set(ids)):
        raise ValueError("Watch ids must be unique")
    return watches
