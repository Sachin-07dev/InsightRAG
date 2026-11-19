# ruff: noqa: E501
"""Synthetic, provider-free ranking, validation, citation and evaluation tests."""

import json
from uuid import uuid4

import httpx
import pytest
from insightrag.retrieval.context import assemble_context, verify_citations
from insightrag.retrieval.evaluation import evaluate_ranking
from insightrag.retrieval.provider import CompatibleChatGenerator, GenerationUnavailable
from insightrag.retrieval.query import prepare_query, resolve_followup
from insightrag.retrieval.ranking import (
    Candidate,
    maximal_marginal_relevance,
    reciprocal_rank_fusion,
)


def candidate(position: int, vector: tuple[float, ...] = (1.0, 0.0)) -> Candidate:
    return Candidate(
        uuid4(),
        uuid4(),
        position,
        "Synthetic",
        1,
        uuid4(),
        f"Evidence {position}",
        "page:1",
        None,
        embedding=vector,
    )


def test_query_normalization_and_analytics_handoff():
    assert prepare_query("  Delhi\u00a0report  ").normalized == "Delhi report"
    assert prepare_query("Total sales in Delhi?").kind == "analytics"
    assert resolve_followup("What about it?", "What is the policy?").startswith(
        "What is the policy?"
    )
    with pytest.raises(ValueError):
        prepare_query("\x00bad")


def test_rrf_deduplicates_and_rewards_two_channels():
    a, b = candidate(0), candidate(1)
    fused = reciprocal_rank_fusion([a, b], [b, a], limit=2, rank_constant=60)
    assert {item.key for item in fused} == {a.key, b.key}
    assert all(item.channels == ("dense", "sparse") for item in fused)
    assert fused[0].fusion_score == pytest.approx(1 / 61 + 1 / 62)


def test_mmr_diversifies():
    a = candidate(0, (0.9, 0.1))
    duplicate = candidate(1, (0.9, 0.1))
    diverse = candidate(2, (0.7, -0.7))
    selected = maximal_marginal_relevance([a, duplicate, diverse], (1.0, 0.0), limit=2, weight=0.5)
    assert selected[0] in (a, duplicate)
    assert selected[1] == diverse


def test_context_budget_and_citation_integrity():
    a = candidate(0)
    evidence, context = assemble_context(uuid4(), [a, a], max_tokens=100, limit=2)
    assert len(evidence) == 1 and evidence[0].citation_id in context
    assert verify_citations([evidence[0].citation_id], evidence)
    assert not verify_citations(["src_forged"], evidence)


def test_retrieval_metrics():
    result = evaluate_ranking(["x", "a", "b"], {"a", "b"}, k=3)
    assert result.precision_at_k == pytest.approx(2 / 3)
    assert result.recall_at_k == 1
    assert result.reciprocal_rank == 0.5
    assert result.average_precision == pytest.approx((1 / 2 + 2 / 3) / 2)
    assert 0 < result.ndcg_at_k < 1


async def test_chat_adapter_validates_json_contract_and_completion_status():
    captured = {}

    def success(request):
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "Finance approves it.",
                                    "citation_ids": ["src_real"],
                                    "uncertainty": None,
                                }
                            ),
                            "refusal": None,
                        },
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    generator = CompatibleChatGenerator(
        "https://synthetic.invalid/chat",
        "secret",
        "synthetic-model",
        transport=httpx.MockTransport(success),
    )
    result = await generator.generate("Who approves?", "[src_real] Finance approves it.")
    assert result.draft.citation_ids == ["src_real"]
    assert (result.prompt_tokens, result.completion_tokens) == (20, 5)
    assert captured["max_completion_tokens"] == 800 and captured["store"] is False
    assert "temperature" not in captured

    def truncated(request):
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        )

    broken = CompatibleChatGenerator(
        "https://synthetic.invalid/chat",
        "secret",
        "synthetic-model",
        transport=httpx.MockTransport(truncated),
    )
    with pytest.raises(GenerationUnavailable):
        await broken.generate("Who approves?", "evidence")
