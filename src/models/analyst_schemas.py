from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CodeExecutionAttempt(BaseModel):
    attempt_number: int
    code: str
    stdout: str = ""
    stderr: str = ""
    success: bool = False


class AnalysisResult(BaseModel):
    executive_summary: str = ""
    key_insights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    chart_json: dict[str, Any] | None = None
    attempts: list[CodeExecutionAttempt] = Field(default_factory=list)
    succeeded: bool = False
