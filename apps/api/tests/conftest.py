import pytest
from fastapi.testclient import TestClient
from insightrag.core.config import Settings
from insightrag.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="test")


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client
