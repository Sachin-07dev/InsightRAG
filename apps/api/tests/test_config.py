import pytest
from insightrag.core.config import Settings
from pydantic import ValidationError


def test_file_secrets_load_but_do_not_appear_in_repr(tmp_path):
    file = tmp_path / "database_url"
    file.write_text("postgresql+asyncpg://test:canary-secret@localhost/test", encoding="utf-8")
    settings = Settings(_env_file=None, database_url_file=file)
    assert "canary-secret" not in repr(settings)
    assert settings.database_url.get_secret_value().endswith("@localhost/test")


def test_conflicting_secret_sources_and_empty_files_fail(tmp_path):
    file = tmp_path / "secret"
    file.write_text("", encoding="utf-8")
    with pytest.raises(ValidationError, match="not both"):
        Settings(_env_file=None, redis_url="redis://localhost", redis_url_file=file)
    with pytest.raises(ValidationError, match="Empty redis_url"):
        Settings(_env_file=None, redis_url_file=file)


def test_invalid_url_errors_do_not_expose_secret():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, database_url="invalid://canary-secret")
    assert "canary-secret" not in str(exc.value)


def test_production_requires_dependencies_and_pool_bounds():
    with pytest.raises(ValidationError, match="Production requires"):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, pool_size=0)
