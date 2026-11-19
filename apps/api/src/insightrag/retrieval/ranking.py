"""Score-agnostic fusion and optional diversity selection."""
# ruff: noqa: E501

import math
from dataclasses import dataclass, replace
from uuid import UUID


@dataclass(frozen=True)
class Candidate:
    resource_id: UUID
    version_id: UUID
    position: int
    title: str
    version_number: int
    workspace_id: UUID
    text: str
    locator: str
    heading: str | None
    embedding: tuple[float, ...] | None = None
    distance: float | None = None
    sparse_score: float | None = None
    fusion_score: float = 0.0
    channels: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[UUID, UUID, int]:
        return self.resource_id, self.version_id, self.position


def reciprocal_rank_fusion(
    dense: list[Candidate], sparse: list[Candidate], *, limit: int, rank_constant: int = 60
) -> list[Candidate]:
    if limit < 1 or rank_constant < 1:
        raise ValueError("Invalid fusion configuration")
    merged: dict[tuple[UUID, UUID, int], Candidate] = {}
    for channel, candidates in (("dense", dense), ("sparse", sparse)):
        for rank, candidate in enumerate(candidates, 1):
            previous = merged.get(candidate.key, candidate)
            merged[candidate.key] = replace(
                previous,
                fusion_score=previous.fusion_score + 1 / (rank_constant + rank),
                channels=tuple(sorted(set(previous.channels) | {channel})),
                distance=candidate.distance if channel == "dense" else previous.distance,
                sparse_score=candidate.sparse_score
                if channel == "sparse"
                else previous.sparse_score,
                embedding=candidate.embedding or previous.embedding,
            )
    return sorted(
        merged.values(),
        key=lambda item: (
            -item.fusion_score,
            str(item.resource_id),
            str(item.version_id),
            item.position,
        ),
    )[:limit]


def cosine(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    if len(first) != len(second):
        raise ValueError("Vector dimensions differ")
    numerator = sum(a * b for a, b in zip(first, second, strict=True))
    denominator = math.sqrt(sum(a * a for a in first) * sum(b * b for b in second))
    return numerator / denominator if denominator else 0.0


def maximal_marginal_relevance(
    candidates: list[Candidate], query_vector: tuple[float, ...], *, limit: int, weight: float
) -> list[Candidate]:
    if not 0 <= weight <= 1 or limit < 1:
        raise ValueError("Invalid MMR configuration")
    remaining = list(candidates)
    selected: list[Candidate] = []
    while remaining and len(selected) < limit:

        def score(item: Candidate) -> float:
            if item.embedding is None:
                return -math.inf
            relevance = cosine(query_vector, item.embedding)
            redundancy = max(
                (
                    cosine(item.embedding, chosen.embedding)
                    for chosen in selected
                    if chosen.embedding
                ),
                default=0.0,
            )
            return weight * relevance - (1 - weight) * redundancy

        chosen = min(
            remaining, key=lambda item: (-score(item), str(item.resource_id), item.position)
        )
        selected.append(chosen)
        remaining.remove(chosen)
    return selected
