"""Formats retrieved chunks into a de-duplicated source list for the UI."""
from __future__ import annotations

from typing import Any


def format_sources(chunks: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for chunk in chunks:
        source = chunk.get("source_document")
        if source and source not in seen:
            seen.append(source)
    return seen
