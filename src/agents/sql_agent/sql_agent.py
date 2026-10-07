"""
SQL Agent: converts natural language into Athena SQL, executes it, and
returns structured results.
"""
from __future__ import annotations

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.sql_agent.sql_validator import extract_last_executed_sql
from src.config.constants import AgentName
from src.llm.llm_factory import get_deterministic_model
from src.models.agent_io_schemas import AgentRequest, AgentResponse, AgentStatus
from src.prompts.sql_agent_prompts import SQL_AGENT_SYSTEM_PROMPT
from src.tools.tool_registry import SQL_AGENT_TOOLS
from src.utils.tool_results import extract_tool_payloads


class SQLAgent(BaseAgent):
    name = AgentName.SQL_AGENT

    def __init__(self) -> None:
        super().__init__()
        self._strands_agent = Agent(
            model=get_deterministic_model(),
            tools=SQL_AGENT_TOOLS,
            system_prompt=SQL_AGENT_SYSTEM_PROMPT,
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

            tool_results = extract_tool_payloads(self._strands_agent, since_index=history_mark)

            # The model sometimes answers with SQL text instead of executing
            # it. Force one retry that must go through the tool.
            if not tool_results:
                self._log(request.trace_id, "no_tool_call_retry", level="WARNING")
                result = self._strands_agent(
                    "You did not execute any query. Call the `run_athena_query` tool now "
                    "with the SQL needed to answer the question, then summarise the results. "
                    "Do not return SQL for the user to run."
                )
                answer_text = str(result)
                tool_results = extract_tool_payloads(self._strands_agent, since_index=history_mark)

            generated_sql = extract_last_executed_sql(tool_results)
            errors = [r for r in tool_results if "error" in r]

            successes = [r for r in tool_results if "error" not in r]
            latest_success = successes[-1] if successes else None

            response.data = {
                "answer": answer_text,
                "generated_sql": generated_sql,
                "columns": latest_success.get("columns", []) if latest_success else [],
                "rows": latest_success.get("rows", []) if latest_success else [],
                "row_count": latest_success.get("row_count", 0) if latest_success else 0,
                # Every successful query, not just the last one: multi-part
                # questions (by trial + by month + by severity) need all of
                # them downstream, otherwise the Analyst only sees one slice.
                "result_sets": [
                    {
                        "sql": r.get("sql"),
                        "columns": r.get("columns", []),
                        "rows": r.get("rows", []),
                        "row_count": r.get("row_count", 0),
                    }
                    for r in successes
                ],
            }

            if errors and not latest_success:
                response.status = AgentStatus.FAILED
                response.error = errors[-1].get("error")
                response.add_step(self.name, "failed", response.error or "")
            elif not tool_results:
                # No query ran, so any numbers in answer_text are unverified. Don't
                # pass them off as data-backed.
                response.status = AgentStatus.FAILED
                response.error = "SQL agent answered without executing a query."
                response.data["answer"] = ""
                response.add_step(self.name, "failed", "No query was executed")
            else:
                response.add_step(self.name, "completed", f"{response.data['row_count']} rows returned")

            self._log(request.trace_id, "completed", sql=generated_sql, row_count=response.data.get("row_count"))
            return response

        except Exception as exc:  # noqa: BLE001
            self._log(request.trace_id, "failed", level="ERROR", error=str(exc))
            response.status = AgentStatus.FAILED
            response.error = str(exc)
            response.add_step(self.name, "failed", str(exc))
            return response
