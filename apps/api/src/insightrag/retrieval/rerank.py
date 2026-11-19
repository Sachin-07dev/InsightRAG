"""Optional provider-independent authorized-candidate reranking."""
# ruff: noqa: E501

import math
from typing import Protocol

import httpx

from insightrag.retrieval.ranking import Candidate


class RerankUnavailable(RuntimeError):
    pass


class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]: ...


class CompatibleReranker:
    """Expects {scores:[float,...]}; only authorized candidates reach this adapter."""

    def __init__(self, endpoint: str, api_key: str, model: str) -> None:
        if not endpoint.startswith("https://") or not api_key or not model:
            raise ValueError("Invalid reranker configuration")
        self.endpoint, self.api_key, self.model = endpoint, api_key, model

    async def rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return []
        try:
            async with httpx.AsyncClient(
                timeout=10, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": [item.text for item in candidates],
                    },
                )
                response.raise_for_status()
                scores = response.json()["scores"]
                if len(scores) != len(candidates) or any(
                    not isinstance(score, (int, float))
                    or isinstance(score, bool)
                    or not math.isfinite(score)
                    for score in scores
                ):
                    raise ValueError("Invalid reranker scores")
                return [
                    item
                    for _, item in sorted(
                        zip(scores, candidates, strict=True),
                        key=lambda pair: (-pair[0], str(pair[1].resource_id), pair[1].position),
                    )
                ]
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise RerankUnavailable("Reranker unavailable") from None
