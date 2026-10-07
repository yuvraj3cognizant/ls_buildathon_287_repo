"""
Orchestrator Agent: classifies intent, routes to SQL/RAG/Analyst agents
(running SQL + RAG concurrently when both are needed), and composes the
final answer.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.agents.analyst_agent.analyst_agent import AnalystAgent
from src.agents.base_agent import BaseAgent
from src.agents.orchestrator.intent_classifier import classify_intent
from src.agents.rag_agent.rag_agent import RAGAgent
from src.agents.sql_agent.sql_agent import SQLAgent
from src.config.constants import (
    INTERNAL_ERROR_MESSAGE,
    INTERNAL_ERROR_STEP_DETAIL,
    AgentName,
    Intent,
)
from src.models.agent_io_schemas import AgentRequest, AgentResponse, AgentStatus
from src.prompts.orchestrator_prompts import FINAL_ANSWER_SYSTEM_PROMPT
from src.services.bedrock_service import invoke_converse
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OrchestratorAgent(BaseAgent):
    name = AgentName.ORCHESTRATOR

    def __init__(self) -> None:
        super().__init__()
        # Built on first use, not here. Constructing a Strands Agent creates a
        # BedrockModel + boto3 client and loads the tool registry; doing that
        # for all three up front cost seconds even for questions that only
        # need one of them.
        self._agents: dict[str, BaseAgent] = {}

    @property
    def sql_agent(self) -> SQLAgent:
        if "sql" not in self._agents:
            self._agents["sql"] = SQLAgent()
        return self._agents["sql"]

    @property
    def rag_agent(self) -> RAGAgent:
        if "rag" not in self._agents:
            self._agents["rag"] = RAGAgent()
        return self._agents["rag"]

    @property
    def analyst_agent(self) -> AnalystAgent:
        if "analyst" not in self._agents:
            self._agents["analyst"] = AnalystAgent()
        return self._agents["analyst"]

    def run(self, request: AgentRequest, on_step=None) -> dict[str, Any]:
        """Returns a dict with the full multi-agent execution result, shaped
        for direct consumption by the Streamlit UI:

        {
          "final_answer": str,
          "intent": dict,
          "sql_response": AgentResponse | None,
          "rag_response": AgentResponse | None,
          "analyst_response": AgentResponse | None,
          "execution_trace": [ExecutionStep, ...]  # merged, chronological
        }
        """
        trace: list = []

        def emit(step: dict) -> None:
            """Record a step and push it to the caller's live listener. A
            broken listener must never fail the run, so callbacks are
            best-effort. Failure details are replaced with a generic message:
            the raw error is already logged by the agent and must not reach
            the UI."""
            if step.get("event") == "failed":
                step = {**step, "detail": INTERNAL_ERROR_STEP_DETAIL}
            trace.append(step)
            if on_step is not None:
                try:
                    on_step(step)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("on_step listener raised, ignoring: %s", exc)

        self._log(request.trace_id, "started", question=request.user_question)
        emit({"agent": self.name, "event": "started", "detail": request.user_question})

        try:
            return self._run(request, emit, trace)
        except Exception as exc:  # noqa: BLE001
            # Last line of defence: nothing raised anywhere in the pipeline may
            # reach the UI as a stack trace or raw error string.
            logger.exception("Orchestrator run failed (trace_id=%s)", request.trace_id)
            self._log(request.trace_id, "failed", level="ERROR", error=str(exc))
            emit({"agent": self.name, "event": "failed", "detail": str(exc)})
            return self._internal_error_result({}, None, None, None, trace)

    def _run(self, request: AgentRequest, emit, trace: list) -> dict[str, Any]:
        intent_info = classify_intent(request.user_question)
        emit({"agent": self.name, "event": "intent_classified", "detail": intent_info})
        self._log(request.trace_id, "intent_classified", **intent_info)

        sql_response: AgentResponse | None = None
        rag_response: AgentResponse | None = None
        analyst_response: AgentResponse | None = None

        requires_sql = intent_info.get("requires_sql", False)
        requires_rag = intent_info.get("requires_rag", False)
        # Driven by the orthogonal `requires_analysis` flag, NOT by the intent
        # label. Keying off `intent == ANALYTICAL` meant a HYBRID question that
        # asked for a chart never reached the Analyst Agent.
        is_analytical = intent_info.get(
            "requires_analysis", intent_info.get("intent") == Intent.ANALYTICAL
        )

        # Run SQL + RAG concurrently when both are needed. Agents are built
        # eagerly here (outside the pool) so two threads can't race to
        # construct the same lazily-initialized agent.
        # The sequential branch emits its steps as it goes (so the UI shows
        # RAG finishing before SQL starts); the other branches emit afterwards.
        steps_already_emitted = False

        if requires_sql and requires_rag and intent_info.get("sql_depends_on_rag"):
            # RAG FIRST, then SQL with the retrieved criteria injected. Running
            # these in parallel meant the SQL Agent had to guess the filter
            # conditions (e.g. a trial's inclusion criteria) that only the
            # documents define, so it answered a different question.
            emit({"agent": self.name, "event": "tool_call",
                  "detail": "SQL depends on document context — running RAG first"})
            rag_response = self.rag_agent.run(request)
            for step in rag_response.execution_trace:
                emit(step.model_dump())

            sql_request = self._augment_with_rag(request, rag_response)
            emit({"agent": self.name, "event": "tool_call",
                  "detail": "Running SQL with retrieved document context"})
            sql_response = self.sql_agent.run(sql_request)
            for step in sql_response.execution_trace:
                emit(step.model_dump())
            steps_already_emitted = True
        elif requires_sql and requires_rag:
            sql_agent, rag_agent = self.sql_agent, self.rag_agent
            with ThreadPoolExecutor(max_workers=2) as pool:
                sql_future = pool.submit(sql_agent.run, request)
                rag_future = pool.submit(rag_agent.run, request)
                sql_response = self._settle(sql_future, AgentName.SQL_AGENT, request)
                rag_response = self._settle(rag_future, AgentName.RAG_AGENT, request)
        elif requires_sql:
            sql_response = self.sql_agent.run(request)
        elif requires_rag:
            rag_response = self.rag_agent.run(request)

        if not steps_already_emitted:
            for r in (sql_response, rag_response):
                if r:
                    for step in r.execution_trace:
                        emit(step.model_dump())

        # Only run the Analyst if there is actually something to analyze.
        # Previously an analytical question whose SQL/RAG step failed still
        # invoked the Code Interpreter with empty context, which burned a
        # self-healing loop and returned a misleading partial result.
        if is_analytical and not self._has_analyzable_data(sql_response, rag_response):
            is_analytical = False
            emit(
                {
                    "agent": self.name,
                    "event": "analyst_skipped",
                    "detail": "No upstream data available to analyze.",
                }
            )
            self._log(request.trace_id, "analyst_skipped")

        if is_analytical:
            analyst_response = self.analyst_agent.run(
                request,
                sql_data=sql_response.data if sql_response else None,
                rag_data=rag_response.data if rag_response else None,
            )
            for step in analyst_response.execution_trace:
                emit(step.model_dump())

        failed_agents = [
            r.agent_name
            for r in (sql_response, rag_response, analyst_response)
            if r is not None and r.status == AgentStatus.FAILED
        ]
        if failed_agents:
            # Any agent failure -> apologise instead of composing a partial or
            # misleading answer from the agents that did succeed.
            self._log(request.trace_id, "failed", level="ERROR", failed_agents=failed_agents)
            emit({"agent": self.name, "event": "failed", "detail": ", ".join(failed_agents)})
            return self._internal_error_result(
                intent_info, sql_response, rag_response, analyst_response, trace
            )

        final_answer = self._compose_final_answer(
            request.user_question, sql_response, rag_response, analyst_response
        )
        emit({"agent": self.name, "event": "completed", "detail": "Final answer composed"})
        self._log(request.trace_id, "completed")

        return {
            "final_answer": final_answer,
            "intent": intent_info,
            "sql_response": sql_response,
            "rag_response": rag_response,
            "analyst_response": analyst_response,
            "execution_trace": trace,
        }

    @staticmethod
    def _internal_error_result(
        intent_info: dict,
        sql_response: AgentResponse | None,
        rag_response: AgentResponse | None,
        analyst_response: AgentResponse | None,
        trace: list,
    ) -> dict[str, Any]:
        return {
            "final_answer": INTERNAL_ERROR_MESSAGE,
            "intent": intent_info,
            "sql_response": sql_response,
            "rag_response": rag_response,
            "analyst_response": analyst_response,
            "execution_trace": trace,
            "internal_error": True,
        }

    def _settle(self, future, agent_name: str, request: AgentRequest) -> AgentResponse:
        """Resolve a parallel agent future, converting a crash into a FAILED
        response instead of aborting the whole orchestration.

        Without this, one agent raising in the pool took down the entire run
        and discarded the other agent's already-completed work.
        """
        try:
            return future.result()
        except Exception as exc:  # noqa: BLE001
            self._log(request.trace_id, "agent_failed", level="ERROR", agent=agent_name, error=str(exc))
            response = AgentResponse(agent_name=agent_name, status=AgentStatus.FAILED, error=str(exc))
            response.add_step(agent_name, "failed", str(exc))
            return response

    @staticmethod
    def _augment_with_rag(request: AgentRequest, rag_response: AgentResponse) -> AgentRequest:
        """Build the SQL Agent's request with the RAG findings prepended, so
        the generated SQL filters on criteria actually taken from the
        documents rather than invented."""
        if rag_response.status == AgentStatus.FAILED:
            return request

        criteria = (rag_response.data or {}).get("answer") or ""
        if not criteria.strip():
            return request

        # This instruction is deliberately forceful and states the failure mode
        # explicitly. A softer "use this context" phrasing caused the agent to
        # treat the criteria as background and emit an unfiltered COUNT(*) for
        # the trial — the right trial, the wrong cohort.
        augmented = (
            f"USER QUESTION: {request.user_question}\n\n"
            "ELIGIBILITY CRITERIA extracted from the trial protocol documents:\n"
            "---\n"
            f"{criteria[:4000]}\n"
            "---\n\n"
            "MANDATORY REQUIREMENTS for your SQL:\n"
            "1. Break the criteria above into individual, checkable conditions "
            "(age ranges, lab-value thresholds, diagnoses, prior-treatment rules, "
            "exclusions).\n"
            "2. Translate EVERY condition you can map to an available column into "
            "an explicit predicate in the WHERE clause. Inspect the table schema "
            "first to find the right columns.\n"
            "3. Exclusion criteria must be negated (NOT / <> / NOT IN), not ignored.\n"
            "4. A bare count filtered only by trial id is a WRONG ANSWER. The whole "
            "point is to count only patients who MEET THESE CRITERIA, not every "
            "patient enrolled in the trial.\n"
            "5. In your final response, list each criterion and state how you "
            "encoded it in SQL — or say explicitly that no column supports it. "
            "Never silently drop a criterion.\n"
        )
        return request.model_copy(update={"user_question": augmented})

    @staticmethod
    def _has_analyzable_data(
        sql_response: AgentResponse | None, rag_response: AgentResponse | None
    ) -> bool:
        if sql_response and sql_response.status != AgentStatus.FAILED:
            if sql_response.data.get("rows"):
                return True
        if rag_response and rag_response.status != AgentStatus.FAILED:
            if rag_response.data.get("chunks") or rag_response.data.get("answer"):
                return True
        return False

    @staticmethod
    def _compose_final_answer(
        user_question: str,
        sql_response: AgentResponse | None,
        rag_response: AgentResponse | None,
        analyst_response: AgentResponse | None,
    ) -> str:
        import json

        parts = {}
        if sql_response:
            parts["sql_agent_output"] = {
                "status": sql_response.status,
                "answer": sql_response.data.get("answer"),
                "row_count": sql_response.data.get("row_count"),
            }
        if rag_response:
            parts["rag_agent_output"] = {
                "status": rag_response.status,
                "answer": rag_response.data.get("answer"),
                "sources": rag_response.data.get("sources"),
            }
        if analyst_response:
            parts["analyst_agent_output"] = {
                "status": analyst_response.status,
                "executive_summary": analyst_response.data.get("executive_summary"),
                "key_insights": analyst_response.data.get("key_insights"),
                "risks": analyst_response.data.get("risks"),
                "recommendations": analyst_response.data.get("recommendations"),
            }

        if not parts:
            return "I was unable to determine how to answer this question."

        # Latency: with a single successful agent there is nothing to
        # synthesize across, so the composition call is a whole extra Bedrock
        # round trip that only rephrases text we already have. Return it directly.
        if len(parts) == 1 and analyst_response is None:
            only = next(iter(parts.values()))
            if only.get("status") != AgentStatus.FAILED and only.get("answer"):
                return only["answer"]

        user_prompt = (
            f"User question: {user_question}\n\n"
            f"Agent outputs:\n{json.dumps(parts, default=str)[:6000]}"
        )
        try:
            return invoke_converse(FINAL_ANSWER_SYSTEM_PROMPT, user_prompt, temperature=0.2, max_tokens=1024)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Final answer composition failed, falling back to raw concatenation: %s", exc)
            fallback_bits = []
            if sql_response and sql_response.data.get("answer"):
                fallback_bits.append(sql_response.data["answer"])
            if rag_response and rag_response.data.get("answer"):
                fallback_bits.append(rag_response.data["answer"])
            if analyst_response and analyst_response.data.get("executive_summary"):
                fallback_bits.append(analyst_response.data["executive_summary"])
            return "\n\n".join(fallback_bits) or "No answer could be composed."
