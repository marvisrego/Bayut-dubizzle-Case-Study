"""Environment-backed settings. Secret fields are never included in repr output."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url


@dataclass(frozen=True)
class Settings:
    db_user: str
    db_password: str = field(repr=False)
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "postgres"
    db_url: URL | None = field(default=None, repr=False)
    qdrant_url: str = field(default="", repr=False)
    qdrant_key: str = field(default="", repr=False)
    nvidia_key: str = field(default="", repr=False)
    nvidia_llm_key: str = field(default="", repr=False)
    nvidia_model: str = "nvidia/nemotron-3-embed-1b"
    nvidia_url: str = "https://integrate.api.nvidia.com/v1/embeddings"
    nvidia_llm_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nvidia_llm_url: str = "https://integrate.api.nvidia.com/v1/chat/completions"
    nvidia_batch_size: int = 189
    nvidia_requests_per_minute: int = 40
    qdrant_collection: str = "Dubizzle-collection"

    @property
    def sqlalchemy_url(self) -> URL:
        return self.db_url or URL.create(
            "postgresql+psycopg2",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_settings(
    env_path: Path | None = None, *, require_vector: bool = True
) -> Settings:
    load_dotenv(
        env_path or Path(__file__).resolve().parents[2] / ".env", override=False
    )
    raw_link = _required("Supabase_Link")
    if "://" in raw_link:
        parsed = make_url(raw_link)
        if parsed.drivername not in ("postgres", "postgresql", "postgresql+psycopg2"):
            raise ValueError("Supabase_Link must be a PostgreSQL URI")
        if not parsed.host or not parsed.username or not parsed.database:
            raise ValueError(
                "Supabase_Link is missing PostgreSQL host, user, or database"
            )
        db_url = parsed.set(
            drivername="postgresql+psycopg2",
            password=parsed.password or _required("Supabase_Pass"),
        )
        host = db_url.host
        user = db_url.username
        password = db_url.password
        port = db_url.port or 5432
        database = db_url.database
    else:
        host = raw_link
        if not host or "/" in host or "@" in host:
            raise ValueError("Supabase_Link must contain only the database host")
        user = _required("user")
        password = _required("Supabase_Pass")
        port = int(_required("port"))
        database = _required("database")
        db_url = None
    # All 189 current workbook texts were successfully tested in one provider call.
    batch_size = int(os.getenv("NVIDIA_EMBED_BATCH_SIZE", "189"))
    rate_limit = int(os.getenv("NVIDIA_REQUESTS_PER_MINUTE", "40"))
    if batch_size < 1 or port < 1 or port > 65535 or rate_limit < 1:
        raise ValueError("Invalid port, embedding batch size, or request rate")
    return Settings(
        db_user=user,
        db_password=password,
        db_host=host,
        db_port=port,
        db_name=database,
        db_url=db_url,
        qdrant_url=_required("Vector_DB_Endpoint")
        if require_vector
        else os.getenv("Vector_DB_Endpoint", ""),
        qdrant_key=_required("Vector_DB_Key")
        if require_vector
        else os.getenv("Vector_DB_Key", ""),
        nvidia_key=_required("nvidia_embed_model_key")
        if require_vector
        else os.getenv("nvidia_embed_model_key", ""),
        nvidia_llm_key=os.getenv("nvidia_LLM_model_key", "").strip(),
        nvidia_model=os.getenv(
            "NVIDIA_EMBED_MODEL", "nvidia/nemotron-3-embed-1b"
        ).strip(),
        nvidia_url=os.getenv(
            "NVIDIA_EMBED_URL", "https://integrate.api.nvidia.com/v1/embeddings"
        ).strip(),
        nvidia_llm_model=os.getenv(
            "NVIDIA_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b"
        ).strip(),
        nvidia_llm_url=os.getenv(
            "NVIDIA_LLM_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
        ).strip(),
        nvidia_batch_size=batch_size,
        nvidia_requests_per_minute=min(40, rate_limit),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "Dubizzle-collection").strip(),
    )
