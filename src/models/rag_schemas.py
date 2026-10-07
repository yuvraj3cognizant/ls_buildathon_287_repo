from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    content: str
    source_document: str
    score: float | None = None
    location: str | None = None


class RAGResult(BaseModel):
    answer: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
