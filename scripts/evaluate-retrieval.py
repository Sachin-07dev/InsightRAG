"""Offline ranking demonstration; does not benchmark providers or a live corpus."""

import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from insightrag.retrieval.evaluation import evaluate_ranking
from insightrag.retrieval.ranking import Candidate, reciprocal_rank_fusion


def candidate(name: str) -> Candidate:
    key = uuid5(NAMESPACE_URL, "synthetic-rag:" + name)
    return Candidate(key, key, 0, name, 1, key, name, "line:1", None)


def main() -> None:
    path = Path(__file__).resolve().parent.parent / "apps/api/tests/fixtures/rag_rankings.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    results = {}
    for strategy in ("dense", "sparse", "hybrid"):
        rows = []
        started = perf_counter()
        for case in fixture["cases"]:
            if strategy == "hybrid":
                ranked = [
                    item.title
                    for item in reciprocal_rank_fusion(
                        [candidate(name) for name in case["dense"]],
                        [candidate(name) for name in case["sparse"]],
                        limit=3,
                    )
                ]
            else:
                ranked = case[strategy]
            rows.append(evaluate_ranking(ranked, set(case["relevant"]), k=3))
        results[strategy] = {
            "mrr": round(mean(row.reciprocal_rank for row in rows), 4),
            "recall_at_3": round(mean(row.recall_at_k for row in rows), 4),
            "ndcg_at_3": round(mean(row.ndcg_at_k for row in rows), 4),
            "local_ranking_ms": round((perf_counter() - started) * 1000, 3),
        }
    print(
        json.dumps(
            {"dataset": fixture["version"], "cases": len(fixture["cases"]), "results": results},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
