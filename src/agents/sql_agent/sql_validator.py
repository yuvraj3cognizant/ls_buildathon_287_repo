"""Extracts and re-validates the SQL actually executed by the SQL Agent's tool
calls, for surfacing in the Streamlit UI's "Generated SQL" panel."""
from __future__ import annotations

from typing import Any


def extract_last_executed_sql(tool_results: list[dict[str, Any]]) -> str | None:
    """Given a list of run_athena_query tool result dicts, return the SQL of
    the last successful execution (or the last attempted SQL if all failed).
    """
    if not tool_results:
        return None
    for result in reversed(tool_results):
        if "sql" in result and "error" not in result:
            return result["sql"]
    return tool_results[-1].get("sql")
