"""Export the development contract without connecting to any service."""

import json
from pathlib import Path

from insightrag.core.config import Settings
from insightrag.main import create_app

settings = Settings(
    _env_file=None,
    environment="test",
    database_url=None,
    database_url_file=None,
    redis_url=None,
    redis_url_file=None,
    migration_database_url=None,
    migration_database_url_file=None,
)
output = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"
output.write_text(json.dumps(create_app(settings).openapi(), indent=2) + "\n", encoding="utf-8")
print("Exported docs/api/openapi.json (development/test foundation contract)")
