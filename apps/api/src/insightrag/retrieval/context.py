"""Token-bounded evidence with stable opaque citation labels."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import tiktoken

from insightrag.retrieval.ranking import Candidate


def tokenizer() -> tiktoken.Encoding:
    os.environ.setdefault(
        "TIKTOKEN_CACHE_DIR", str(Path(__file__).parent.parent / "ingestion" / "assets")
    )
    return tiktoken.get_encoding("cl100k_base")


def citation_id(org_id: UUID, candidate: Candidate) -> str:
    value = f"{org_id}:{candidate.resource_id}:{candidate.version_id}:{candidate.position}"
    return "src_" + hashlib.sha256(value.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class Evidence:
    citation_id: str
    candidate: Candidate
    excerpt: str


def assemble_context(
    org_id: UUID, candidates: list[Candidate], *, max_tokens: int, limit: int
) -> tuple[list[Evidence], str]:
    if max_tokens < 64 or limit < 1:
        raise ValueError("Invalid context budget")
    codec = tokenizer()
    selected: list[Evidence] = []
    blocks: list[str] = []
    remaining = max_tokens
    seen: set[tuple[UUID, UUID, str]] = set()
    for item in candidates:
        if len(selected) >= limit:
            break
        normalized = " ".join(item.text.split())
        dedup_key = (item.resource_id, item.version_id, normalized)
        if dedup_key in seen:
            continue
        label = citation_id(org_id, item)
        header = f"[{label}] {item.title} v{item.version_number} {item.locator}\n"
        header_tokens = len(codec.encode(header)) + 4
        if remaining <= header_tokens + 16:
            break
        tokens = codec.encode(item.text)
        excerpt = codec.decode(tokens[: remaining - header_tokens])
        if not excerpt.strip():
            continue
        block = header + excerpt
        remaining -= len(codec.encode(block)) + 4
        selected.append(Evidence(label, item, excerpt))
        blocks.append(block)
        seen.add(dedup_key)
    return selected, "\n\n".join(blocks)


def verify_citations(ids: list[str], evidence: list[Evidence]) -> bool:
    allowed = {item.citation_id: item for item in evidence}
    return bool(ids) and all(
        citation in allowed and allowed[citation].excerpt in allowed[citation].candidate.text
        for citation in ids
    )
