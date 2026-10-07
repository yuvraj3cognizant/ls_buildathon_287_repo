"""
Analyst Agent: consumes SQL Agent / RAG Agent outputs, plans an analysis,
generates and self-heals Python code executed in AgentCore Code Interpreter,
and produces executive summary + insights + risks + recommendations + chart.
"""
from __future__ import annotations

from typing import Any

from src.agents.analyst_agent.planner import create_analysis_plan
from src.agents.analyst_agent.self_healing_loop import run_self_healing_analysis
from src.agents.base_agent import BaseAgent
from src.config.constants import AgentName
from src.models.agent_io_schemas import AgentRequest, AgentResponse, AgentStatus
from src.prompts.analyst_agent_prompts import INSIGHT_GENERATOR_SYSTEM_PROMPT
from src.services.bedrock_service import invoke_converse_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalystAgent(BaseAgent):
    name = AgentName.ANALYST_AGENT

    def run(
        self,
        request: AgentRequest,
        sql_data: dict[str, Any] | None = None,
        rag_data: dict[str, Any] | None = None,
    ) -> AgentResponse:
        response = AgentResponse(agent_name=self.name, status=AgentStatus.SUCCESS)
        response.add_step(self.name, "started", request.user_question)
        self._log(request.trace_id, "started", question=request.user_question)

        context_data = self._collect_context(sql_data, rag_data)

        try:
            response.add_step(self.name, "tool_call", "Creating analysis plan")
            plan = create_analysis_plan(request.user_question, context_data)
            self._log(request.trace_id, "plan_created", plan=plan)

            response.add_step(self.name, "tool_call", "Executing analysis in Code Interpreter")
            execution_result = run_self_healing_analysis(plan, context_data)

            if not execution_result["success"]:
                response.status = AgentStatus.PARTIAL
                response.add_step(
                    self.name, "failed",
                    f"Analysis code failed after {len(execution_result['attempts'])} attempt(s)",
                )
                response.data = {
                    "plan": plan,
                    "attempts": [a.model_dump() for a in execution_result["attempts"]],
                    "executive_summary": (
                        "The analysis could not be completed automatically after "
                        "multiple retries. Raw data is available for manual review."
                    ),
                    "key_insights": [],
                    "risks": ["Automated analysis failed; findings below may be incomplete."],
                    "recommendations": ["Review the raw data manually or refine the question."],
                    "chart_json": None,
                }
                self._log(request.trace_id, "completed_partial", attempts=len(execution_result["attempts"]))
                return response

            findings = execution_result["findings"] or {}
            chart_json = execution_result["chart_json"]

            insights = self._generate_insights(request.user_question, findings, context_data)

            response.data = {
                "plan": plan,
                "findings": findings,
                "chart_json": chart_json,
                "charts": execution_result.get("charts") or ([chart_json] if chart_json else []),
                "attempts": [a.model_dump() for a in execution_result["attempts"]],
                **insights,
            }
            response.add_step(self.name, "completed", "Analysis complete")
            self._log(request.trace_id, "completed", attempt_count=len(execution_result["attempts"]))
            return response

        except Exception as exc:  # noqa: BLE001
            self._log(request.trace_id, "failed", level="ERROR", error=str(exc))
            response.status = AgentStatus.FAILED
            response.error = str(exc)
            response.add_step(self.name, "failed", str(exc))
            return response

    @staticmethod
    def _collect_context(
        sql_data: dict[str, Any] | None, rag_data: dict[str, Any] | None
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        if sql_data:
            context["sql"] = {
                "columns": sql_data.get("columns", []),
                "rows": sql_data.get("rows", []),
                "generated_sql": sql_data.get("generated_sql"),
                # All successful queries (e.g. by trial, by month, by
                # severity). `columns`/`rows` above are the last one only.
                "result_sets": sql_data.get("result_sets", []),
            }
        if rag_data:
            context["rag"] = {
                "answer": rag_data.get("answer"),
                "chunks": [
                    {"content": c.get("content", "")[:1000], "source": c.get("source_document")}
                    for c in rag_data.get("chunks", [])
                ],
            }
        return context

    @staticmethod
    def _generate_insights(
        user_question: str, findings: dict[str, Any], context_data: dict[str, Any]
    ) -> dict[str, Any]:
        import json

        # "Why" questions can only be answered from the documents, so the
        # RAG evidence must reach this step — findings alone are just numbers.
        rag = context_data.get("rag") or {}
        evidence = rag.get("answer") or ""
        user_prompt = (
            f"User question: {user_question}\n\n"
            f"findings:\n{json.dumps(findings, default=str)[:4000]}\n\n"
            f"document_evidence (from trial documents; may be empty):\n{evidence[:3000]}"
        )
        try:
            parsed = invoke_converse_json(INSIGHT_GENERATOR_SYSTEM_PROMPT, user_prompt, temperature=0.2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Insight generation failed, using fallback summary: %s", exc)
            parsed = {
                "executive_summary": "Analysis completed. See findings for details.",
                "key_insights": [],
                "risks": [],
                "recommendations": [],
            }
        parsed.setdefault("executive_summary", "")
        parsed.setdefault("key_insights", [])
        parsed.setdefault("risks", [])
        parsed.setdefault("recommendations", [])
        return parsed
