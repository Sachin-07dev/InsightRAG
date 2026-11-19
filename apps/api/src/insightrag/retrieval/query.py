"""Conservative validation and routing; no silent entity rewriting."""
# ruff: noqa: E501

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class PreparedQuery:
    original: str
    normalized: str
    kind: str


_ANALYTICS = re.compile(
    r"\b(sum|total|average|growth|percentage|percent|ratio|trend|chart|dashboard|"
    r"how many|revenue by|sales by|compare .*sales)\b",
    re.IGNORECASE,
)


def prepare_query(value: str) -> PreparedQuery:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Query exceeds the length limit")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not 3 <= len(normalized) <= 1000 or any(
        unicodedata.category(character) == "Cc" for character in normalized
    ):
        raise ValueError("Query is empty, too long, or contains control characters")
    return PreparedQuery(
        value, normalized, "analytics" if _ANALYTICS.search(normalized) else "document"
    )


def resolve_followup(query: str, previous_question: str | None) -> str:
    if (
        previous_question
        and len(query) < 160
        and re.search(r"\b(it|its|they|their|those|that|this|same)\b", query, re.IGNORECASE)
    ):
        return f"{previous_question}\nFollow-up: {query}"
    return query
