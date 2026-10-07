"""
The self-healing execution loop: generate code -> execute in AgentCore Code
Interpreter -> validate -> on failure, generate a fix and retry (max N) ->
enforce an overall wall-clock deadline.
"""
from __future__ import annotations

from typing import Any

from src.agents.analyst_agent.code_generator import (
    build_executable_snippet,
    generate_analysis_code,
    generate_fixed_code,
)
from src.config.settings import settings
from src.models.analyst_schemas import CodeExecutionAttempt
from src.services import code_interpreter_service
from src.utils.logger import get_logger
from src.utils.timers import Deadline, ExecutionTimeoutError

logger = get_logger(__name__)


def run_self_healing_analysis(
    plan: dict[str, Any],
    context_data: dict[str, Any],
    max_retries: int | None = None,
) -> dict[str, Any]:
    """Returns:
    {
      "success": bool,
      "attempts": [CodeExecutionAttempt, ...],
      "findings": dict | None,
      "chart_json": dict | None,
      "stdout": str,
    }
    """
    max_retries = max_retries if max_retries is not None else settings.max_analyst_retries
    deadline = Deadline(max_seconds=settings.max_execution_seconds)

    attempts: list[CodeExecutionAttempt] = []
    code = generate_analysis_code(plan, context_data)
    last_stderr = ""

    for attempt_number in range(1, max_retries + 1):
        try:
            deadline.check()
        except ExecutionTimeoutError as exc:
            logger.error("Analyst loop hit deadline before attempt %s: %s", attempt_number, exc)
            break

        executable = build_executable_snippet(code, context_data)
        outcome = code_interpreter_service.execute_code_safe(
            executable, timeout_seconds=int(deadline.remaining())
        )

        findings, charts = _extract_findings_and_chart(outcome)
        chart_json = charts[0] if charts else None
        ran_clean = outcome.get("success", False)
        produced_findings = findings is not None
        attempt_success = ran_clean and produced_findings

        stderr = outcome.get("stderr", "")
        if ran_clean and not produced_findings:
            stderr = (
                stderr
                or "Code ran without error but did not print the required "
                "'FINDINGS_JSON::' marker line with a valid findings dict."
            )

        attempt = CodeExecutionAttempt(
            attempt_number=attempt_number,
            code=code,
            stdout=outcome.get("stdout", ""),
            stderr=stderr,
            success=attempt_success,
        )
        attempts.append(attempt)

        if attempt.success:
            return {
                "success": True,
                "attempts": attempts,
                "findings": findings,
                "chart_json": chart_json,
                "charts": charts,
                "stdout": attempt.stdout,
            }

        last_stderr = attempt.stderr
        logger.warning(
            "Analyst code execution attempt %s/%s failed: %s",
            attempt_number,
            max_retries,
            last_stderr[:300],
        )

        if attempt_number < max_retries and not deadline.expired():
            code = generate_fixed_code(code, last_stderr, plan)

    return {
        "success": False,
        "attempts": attempts,
        "findings": None,
        "chart_json": None,
        "charts": [],
        "stdout": "",
        "error": last_stderr or "Analysis failed after all retries.",
    }


def _extract_findings_and_chart(outcome: dict[str, Any]) -> tuple[dict | None, list[dict]]:
    """The generated code is required to print two machine-parseable marker
    lines (FINDINGS_JSON:: / CHART_JSON::) at the end of execution. Parsing
    stdout this way is robust regardless of whether the underlying AgentCore
    SDK version also exposes a structured namespace snapshot.
    """
    import json

    findings: dict | None = None
    charts: list[dict] = []

    stdout = outcome.get("stdout", "")
    for line in stdout.splitlines():
        if line.startswith("FINDINGS_JSON::"):
            try:
                findings = json.loads(line[len("FINDINGS_JSON::"):])
            except json.JSONDecodeError:
                logger.warning("Could not parse FINDINGS_JSON marker line.")
        elif line.startswith("CHART_JSON::"):
            # One line per figure; `null` means no chart.
            try:
                chart = json.loads(line[len("CHART_JSON::"):])
            except json.JSONDecodeError:
                logger.warning("Could not parse CHART_JSON marker line.")
                continue
            if isinstance(chart, dict):
                charts.append(chart)

    # Fall back to structured result payload if the SDK provides one and
    # markers weren't found.
    if findings is None and not charts:
        result = outcome.get("result")
        if isinstance(result, dict):
            findings = result.get("findings")
            if isinstance(result.get("chart_json"), dict):
                charts = [result["chart_json"]]

    return findings, charts
