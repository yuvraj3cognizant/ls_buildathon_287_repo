from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SQLQueryResult(BaseModel):
    generated_sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    athena_query_execution_id: str | None = None
