"""Strands @tool wrappers over the Code Interpreter service, used by the Analyst Agent.

Note: the Analyst Agent's self-healing loop (src/agents/analyst_agent/self_healing_loop.py)
calls `code_interpreter_service.execute_code_safe` directly for tighter control over
retries — this @tool wrapper exists for cases where the Strands agent itself decides
to run code as part of a broader tool-using conversation.
"""
from __future__ import annotations

from strands import tool

from src.services import code_interpreter_service
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def execute_python_analysis(code: str) -> dict:
    """Execute a Python analysis script inside the AgentCore Code Interpreter sandbox.

    Args:
        code: Self-contained Python code. Must assign `findings` (dict) and,
              optionally, `chart_json` (dict, a Plotly figure as a dict).

    Returns:
        A dict with keys: stdout, stderr, success (bool), result.
    """
    outcome = code_interpreter_service.execute_code_safe(code)
    if not outcome["success"]:
        logger.warning("Analyst code execution failed: %s", outcome["stderr"][:500])
    return outcome
