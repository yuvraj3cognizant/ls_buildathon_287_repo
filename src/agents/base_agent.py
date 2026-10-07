"""Shared agent interface. Every specialist agent implements `.run()`."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.agent_io_schemas import AgentRequest, AgentResponse
from src.utils.logger import get_logger, log_event


class BaseAgent(ABC):
    name: str = "base_agent"

    def __init__(self) -> None:
        self.logger = get_logger(f"agent.{self.name}")

    def _log(self, trace_id: str, event: str, level: str = "INFO", **fields) -> None:
        log_event(self.logger, trace_id=trace_id, agent=self.name, event=event, level=level, **fields)

    # Recent chat messages folded into the prompt so follow-ups ("break that down by site")
    # resolve against THIS chat only.
    HISTORY_MESSAGES = 6
    HISTORY_CHARS_PER_MESSAGE = 600

    @staticmethod
    def _reset(strands_agent) -> None:
        """Start every question with an empty model history.

        Agents are cached and shared across questions, chats and users. Left to
        accumulate, the history leaked between users, grew every call slower, and
        let the model answer from earlier turns instead of calling its tools.
        """
        strands_agent.messages.clear()

    def _prompt_with_history(self, request: AgentRequest) -> str:
        history = (request.conversation_history or [])[-self.HISTORY_MESSAGES:]
        if not history:
            return request.user_question
        lines = []
        for m in history:
            content = m.get("content", "")
            if len(content) > self.HISTORY_CHARS_PER_MESSAGE:
                content = content[: self.HISTORY_CHARS_PER_MESSAGE] + "…"
            lines.append(f"{m.get('role', 'user')}: {content}")
        return (
            "Earlier in this conversation (context only, for resolving follow-up references; "
            "do NOT reuse numbers from it, always fetch fresh data with your tools):\n"
            + "\n".join(lines)
            + f"\n\nCurrent question: {request.user_question}"
        )

    @abstractmethod
    def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent's task for the given request and return a typed response."""
        raise NotImplementedError
