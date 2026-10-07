"""Validators for SQL safety and analyst code output shape."""
from __future__ import annotations

import re

from src.utils.exceptions import SQLValidationError

_FORBIDDEN_SQL_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "merge",
    "call",
    "vacuum",
)

_ALLOWED_TABLES = {
    "clinical_trials",
    "patient_data",
    "trial_sites",
    "adverse_events",
    "study_metrics",
}

# Matches the alias in a CTE definition: `WITH foo AS (`, `, bar AS (`.
_CTE_NAME_PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(")


def validate_readonly_sql(sql: str) -> str:
    """Ensure generated SQL is a read-only SELECT against known tables.

    Raises SQLValidationError on any violation. Returns the trimmed SQL on
    success so callers can execute it directly.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Generated SQL is empty.")

    cleaned = sql.strip().rstrip(";")
    lowered = cleaned.lower()

    if not lowered.startswith(("select", "with")):
        raise SQLValidationError(
            "Only SELECT / CTE (WITH) statements are allowed.", context={"sql": sql}
        )

    for keyword in _FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise SQLValidationError(
                f"Forbidden keyword '{keyword}' detected in generated SQL.",
                context={"sql": sql},
            )

    referenced_tables = set(re.findall(r"\bfrom\s+([a-zA-Z0-9_\.]+)", lowered)) | set(
        re.findall(r"\bjoin\s+([a-zA-Z0-9_\.]+)", lowered)
    )
    # Strip db-qualified prefixes (e.g. clinical_db.patient_data -> patient_data)
    referenced_tables = {t.split(".")[-1] for t in referenced_tables}

    # CTE names introduced by `WITH <name> AS (...)` are query-local, not
    # catalog tables, so they must count as allowed references.
    cte_names = set(_CTE_NAME_PATTERN.findall(lowered)) if lowered.startswith("with") else set()

    unknown = referenced_tables - _ALLOWED_TABLES - cte_names
    if unknown:
        raise SQLValidationError(
            f"Query references unknown/disallowed table(s): {unknown}",
            context={"sql": sql},
        )

    return cleaned


def validate_chart_json(chart_json: dict | None) -> bool:
    """Loosely validate that a dict looks like a Plotly figure spec."""
    if not chart_json:
        return False
    return "data" in chart_json and isinstance(chart_json.get("data"), list)
