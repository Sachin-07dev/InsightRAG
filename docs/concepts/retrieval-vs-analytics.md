# Retrieval, analytics and evidence

## What and why

Retrieval selects passages likely to answer a question. It is approximate and usually sees only part of the corpus. Analytics executes a complete, defined computation over an authorized dataset. Confusing them creates fluent but unsupported business numbers.

For 'what is our return policy?', retrieve the relevant policy version and cite it. For 'what were net sales?', execute the approved metric over the relevant dates. For 'why did sales drop?', calculate the drop and retrieve potential explanations, while labeling unsupported causation as a hypothesis.

## Hybrid retrieval internals

Full-text search emphasizes tokens/phrases; embeddings encode semantic similarity. Query both inside the access boundary, then combine rankings with reciprocal rank fusion:

```text
score(item) = sum(1 / (k + rank_in_each_list))
```

The damping constant and candidate counts are evaluation parameters. An initial experiment can fetch 50 candidates/path, rerank up to 40, and keep up to 8 passages. These are not fixed production truth. Remove duplicates, prefer diverse useful evidence, and remain inside the context budget. Small authorized sets can use exact vector scoring; ANN requires filtered-recall measurement.

## Citations and uncertainty

A citation needs a real source version and locator. PDF page indices/display labels differ; DOCX has no stable pagination until rendered. Tables/sheets need meaningful ranges. A valid locator proves existence, not that it supports the claim. Numerical claims point to result/metric/dataset provenance as well as explanatory text where relevant.

Facts, interpretations and recommendations should be presented separately. If records show Delhi revenue fell and a report mentions stockouts, the report supports a possible explanation, not proof that stockouts caused the whole decline.

## Failure and improvement

Empty retrieval -> explicit insufficient evidence. Conflicting versions -> cite authoritative active policy and disclose conflict where relevant. Poor terminology -> evaluate lexical analysis and embedding profile. Lost tables -> improve parser/layout fixtures. Do not fix retrieval by removing ACL filters. Optimize only after labeled quality/latency evidence; see [retrieval module](../modules/retrieval.md).
