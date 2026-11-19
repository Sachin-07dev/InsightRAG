# ruff: noqa: E501
"""Deterministic retrieval metrics for labelled synthetic queries."""

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalMetrics:
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    reciprocal_rank: float
    average_precision: float
    ndcg_at_k: float


def evaluate_ranking(
    ranked: Sequence[str], relevant: set[str], *, k: int, grades: dict[str, int] | None = None
) -> RetrievalMetrics:
    if k < 1:
        raise ValueError("k must be positive")
    top = list(ranked[:k])
    if len(top) != len(set(top)):
        raise ValueError("Ranking contains duplicate identifiers")
    hits = [1 if item in relevant else 0 for item in top]
    count = sum(hits)
    first = next((index for index, hit in enumerate(hits, 1) if hit), None)
    precisions = [sum(hits[:index]) / index for index, hit in enumerate(hits, 1) if hit]
    relevance = grades or {item: 1 for item in relevant}
    dcg = sum(
        (2 ** relevance.get(item, 0) - 1) / math.log2(index + 1)
        for index, item in enumerate(top, 1)
    )
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum((2**grade - 1) / math.log2(index + 1) for index, grade in enumerate(ideal, 1))
    return RetrievalMetrics(
        precision_at_k=count / k,
        recall_at_k=count / len(relevant) if relevant else 0.0,
        hit_rate_at_k=float(count > 0),
        reciprocal_rank=1 / first if first else 0.0,
        average_precision=sum(precisions) / len(relevant) if relevant else 0.0,
        ndcg_at_k=dcg / idcg if idcg else 0.0,
    )
