"""Fixed-dimension, bounded batch embedding provider; no untrusted model-selected endpoint."""

import asyncio
import math
from collections.abc import Sequence
from typing import Protocol

import httpx


class EmbeddingUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    model_id: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def validate_vectors(vectors: list[list[float]], expected_count: int, dimensions: int) -> None:
    if len(vectors) != expected_count or any(
        len(vector) != dimensions
        or not all(math.isfinite(value) for value in vector)
        or math.isclose(sum(value * value for value in vector), 0.0)
        for vector in vectors
    ):
        raise EmbeddingUnavailable("Embedding dimensions or values are invalid")


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model_id: str,
        dimensions: int = 1536,
        batch_size: int = 32,
    ) -> None:
        if (
            not endpoint.startswith("https://")
            or not api_key
            or not model_id
            or dimensions != 1536
            or not 1 <= batch_size <= 64
        ):
            raise ValueError("Invalid embedding provider configuration")
        self.endpoint, self.api_key, self.model_id = endpoint, api_key, model_id
        self.dimensions, self.batch_size = dimensions, batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False) as client:
            for start in range(0, len(texts), self.batch_size):
                batch = list(texts[start : start + self.batch_size])
                for attempt in range(3):
                    try:
                        response = await client.post(
                            self.endpoint,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            json={
                                "model": self.model_id,
                                "input": batch,
                                "dimensions": self.dimensions,
                            },
                        )
                        if response.status_code in (429, 500, 502, 503, 504):
                            raise EmbeddingUnavailable("Embedding provider unavailable")
                        response.raise_for_status()
                        payload = response.json()
                        ordered = sorted(payload["data"], key=lambda item: item["index"])
                        if [item["index"] for item in ordered] != list(range(len(batch))):
                            raise EmbeddingUnavailable("Embedding indexes are invalid")
                        result = [[float(value) for value in item["embedding"]] for item in ordered]
                        validate_vectors(result, len(batch), self.dimensions)
                        vectors.extend(result)
                        break
                    except (httpx.HTTPError, ValueError, KeyError, TypeError, EmbeddingUnavailable):
                        if attempt == 2:
                            raise EmbeddingUnavailable("Embedding provider failed") from None
                        await asyncio.sleep(min(2**attempt, 4))
        return vectors
