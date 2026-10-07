"""
Shared data contracts that flow between agents and into the Streamlit UI.

Agents communicate exclusively through these typed objects rather than raw
strings, so the Orchestrator and the UI can rely on a stable shape.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class ExecutionStep(BaseModel):
    agent: str
    event: str  # started | tool_call | completed | failed | retrying
    detail: str = ""
    timestamp: float = Field(default_factory=time.time)


class AgentRequest(BaseModel):
    session_id: str
    user_question: str
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    trace_id: str


class AgentResponse(BaseModel):
    agent_name: str
    status: AgentStatus
    data: dict[str, Any] = Field(default_factory=dict)
    execution_trace: list[ExecutionStep] = Field(default_factory=list)
    error: Optional[str] = None

    def add_step(self, agent: str, event: str, detail: str = "") -> None:
        self.execution_trace.append(ExecutionStep(agent=agent, event=event, detail=detail))
