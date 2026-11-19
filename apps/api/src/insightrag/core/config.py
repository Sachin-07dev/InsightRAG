"""Explicit environment/file secrets; never log Settings or connection URLs."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INSIGHTRAG_", env_file=".env.local", extra="ignore", hide_input_in_errors=True
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    database_url_file: Path | None = None
    migration_database_url: SecretStr | None = None
    migration_database_url_file: Path | None = None
    redis_url: SecretStr | None = None
    redis_url_file: Path | None = None
    pool_size: int = Field(default=5, ge=1, le=50)
    pool_max_overflow: int = Field(default=5, ge=0, le=50)
    pool_timeout_seconds: float = Field(default=3, gt=0, le=30)
    dependency_timeout_seconds: float = Field(default=2, gt=0, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    rate_limit_per_user: int = Field(default=60, ge=1, le=10000)
    rate_limit_per_organization: int = Field(default=600, ge=1, le=100000)
    upload_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    clamav_host: str | None = None
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    signed_job_key: SecretStr | None = None
    signed_job_key_file: Path | None = None
    object_bucket: str | None = None
    object_region: str | None = None
    object_kms_key_id: str | None = None
    object_endpoint: str | None = None
    embedding_endpoint: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_api_key_file: Path | None = None
    embedding_model: str | None = None
    ingestion_ocr_enabled: bool = False
    generation_endpoint: str | None = None
    generation_api_key: SecretStr | None = None
    generation_api_key_file: Path | None = None
    generation_model: str | None = None
    generation_temperature: float | None = Field(default=None, ge=0, le=2)
    generation_max_completion_tokens: int = Field(default=800, ge=64, le=4096)
    retrieval_dense_k: int = Field(default=20, ge=1, le=100)
    retrieval_sparse_k: int = Field(default=20, ge=1, le=100)
    retrieval_fusion_k: int = Field(default=20, ge=1, le=100)
    retrieval_context_k: int = Field(default=6, ge=1, le=20)
    retrieval_context_tokens: int = Field(default=2400, ge=64, le=12000)
    retrieval_max_cosine_distance: float | None = Field(default=None, ge=0, le=2)
    rerank_endpoint: str | None = None
    rerank_api_key: SecretStr | None = None
    rerank_api_key_file: Path | None = None
    rerank_model: str | None = None
    retrieval_rerank_k: int = Field(default=12, ge=1, le=100)
    orchestration_timeout_seconds: float = Field(default=20, ge=1, le=120)

    @model_validator(mode="after")
    def load_and_validate_secrets(self) -> Self:
        for field in (
            "database_url",
            "migration_database_url",
            "redis_url",
            "signed_job_key",
            "embedding_api_key",
            "generation_api_key",
            "rerank_api_key",
        ):
            direct = getattr(self, field)
            file = getattr(self, f"{field}_file")
            if direct is not None and file is not None:
                raise ValueError(f"Configure {field} or its file, not both")
            if file is not None:
                try:
                    value = file.read_text(encoding="utf-8").strip()
                except OSError:
                    raise ValueError(f"Cannot read {field} secret file") from None
                if not value:
                    raise ValueError(f"Empty {field} secret file")
                setattr(self, field, SecretStr(value))
        for field in ("database_url", "migration_database_url"):
            secret = getattr(self, field)
            if secret:
                try:
                    url = make_url(secret.get_secret_value())
                    if url.drivername != "postgresql+asyncpg" or not url.database or not url.host:
                        raise ValueError
                except Exception:
                    raise ValueError(f"{field} must be a valid postgresql+asyncpg URL") from None
        if self.redis_url and not self.redis_url.get_secret_value().startswith(
            ("redis://", "rediss://")
        ):
            raise ValueError("redis_url must use redis or rediss")
        if self.environment == "production" and (not self.database_url or not self.redis_url):
            raise ValueError("Production requires database and Redis configuration")
        oidc = (self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)
        if any(oidc) and not all(oidc):
            raise ValueError("OIDC requires issuer, audience and JWKS URL together")
        if self.signed_job_key and len(self.signed_job_key.get_secret_value().encode()) < 32:
            raise ValueError("Signed job key requires at least 32 bytes")
        storage = (self.object_bucket, self.object_region, self.object_kms_key_id)
        if any(storage) and not all(storage):
            raise ValueError("Object storage requires bucket, region and KMS key together")
        if self.object_endpoint and not self.object_endpoint.startswith("https://"):
            raise ValueError("Object endpoint must use HTTPS")
        embedding = (self.embedding_endpoint, self.embedding_api_key, self.embedding_model)
        if any(embedding) and not all(embedding):
            raise ValueError("Embedding provider requires endpoint, key and model together")
        if self.embedding_endpoint and not self.embedding_endpoint.startswith("https://"):
            raise ValueError("Embedding endpoint must use HTTPS")
        generation = (self.generation_endpoint, self.generation_api_key, self.generation_model)
        if any(generation) and not all(generation):
            raise ValueError("Generation provider requires endpoint, key and model together")
        if self.generation_endpoint and not self.generation_endpoint.startswith("https://"):
            raise ValueError("Generation endpoint must use HTTPS")
        rerank = (self.rerank_endpoint, self.rerank_api_key, self.rerank_model)
        if any(rerank) and not all(rerank):
            raise ValueError("Reranker requires endpoint, key and model together")
        if self.rerank_endpoint and not self.rerank_endpoint.startswith("https://"):
            raise ValueError("Reranker endpoint must use HTTPS")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production"
