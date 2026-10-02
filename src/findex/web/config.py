from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINDEX_", env_file=".env", extra="ignore"
    )

    index_path: Path = Field(default=Path("web/demo_index.json"))
    docs_path: Path = Field(default=Path("web/demo_docs.jsonl"))
    semantic_embeddings_path: Path = Field(
        default=Path("web/demo_embeddings.npy")
    )
    semantic_metadata_path: Path = Field(
        default=Path("web/demo_embeddings.json")
    )
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "info"
    search_mode: Literal["async", "def"] = "async"


@lru_cache
def get_settings() -> Settings:
    return Settings()
