"""Structure-preserving token-aware chunks; no fabricated page or section locator."""

import os
from dataclasses import dataclass
from pathlib import Path

import tiktoken

from insightrag.ingestion.parsers import Segment


@dataclass(frozen=True)
class Chunk:
    text: str
    locator: str
    heading: str | None
    token_count: int


def chunk_segments(
    segments: tuple[Segment, ...], *, max_tokens: int = 512, overlap: int = 48
) -> tuple[Chunk, ...]:
    if not 32 <= max_tokens <= 2048 or not 0 <= overlap < max_tokens // 2:
        raise ValueError("Invalid chunk budget")
    # The pinned encoding table ships with the package, including in offline workers.
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(__file__).parent / "assets"))
    codec = tiktoken.get_encoding("cl100k_base")
    result: list[Chunk] = []
    current_heading: str | None = None
    for segment in segments:
        if segment.heading:
            current_heading = segment.heading
        tokens = codec.encode(segment.text)
        if not tokens:
            continue
        step = max_tokens - overlap
        for start in range(0, len(tokens), step):
            piece = tokens[start : start + max_tokens]
            if not piece:
                break
            result.append(Chunk(codec.decode(piece), segment.locator, current_heading, len(piece)))
            if start + max_tokens >= len(tokens):
                break
    return tuple(result)
