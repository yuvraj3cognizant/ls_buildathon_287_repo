"""
RAG Agent: searches clinical trial documents via the Bedrock Knowledge Base
and generates grounded answers with citations.
"""
from __future__ import annotations

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.rag_agent.citation_formatter import format_sources
from src.config.constants import AgentName
from src.llm.llm_factory import get_reasoning_model
from src.models.agent_io_schemas import AgentRequest, AgentResponse, AgentStatus
from src.prompts.rag_agent_prompts import RAG_AGENT_SYSTEM_PROMPT
from src.tools.tool_registry import RAG_AGENT_TOOLS
from src.utils.tool_results import extract_tool_payloads


class RAGAgent(BaseAgent):
    name = AgentName.RAG_AGENT

    def __init__(self) -> None:
        super().__init__()
        self._strands_agent = Agent(
            model=get_reasoning_model(),
            tools=RAG_AGENT_TOOLS,
            system_prompt=RAG_AGENT_SYSTEM_PROMPT,
        )

    def run(self, request: AgentRequest) -> AgentResponse:
        response = AgentResponse(agent_name=self.name, status=AgentStatus.SUCCESS)
        response.add_step(self.name, "started", request.user_question)
        self._log(request.trace_id, "started", question=request.user_question)

        try:
            self._reset(self._strands_agent)
            history_mark = 0

            result = self._strands_agent(self._prompt_with_history(request))
            answer_text = str(result)

            chunks: list[dict] = []
            for payload in extract_tool_payloads(self._strands_agent, since_index=history_mark):
                if isinstance(payload.get("chunks"), list):
                    chunks.extend(payload["chunks"])
            sources = format_sources(chunks)

            response.data = {
                "answer": answer_text,
                "chunks": chunks,
                "sources": sources,
            }

            if not chunks:
                response.status = AgentStatus.PARTIAL
                response.add_step(self.name, "completed", "No supporting chunks retrieved")
            else:
                response.add_step(self.name, "completed", f"{len(chunks)} chunks retrieved from {len(sources)} sources")

            self._log(request.trace_id, "completed", chunk_count=len(chunks), sources=sources)
            return response

        except Exception as exc:  # noqa: BLE001
            self._log(request.trace_id, "failed", level="ERROR", error=str(exc))
            response.status = AgentStatus.FAILED
            response.error = str(exc)
            response.add_step(self.name, "failed", str(exc))
            return response
