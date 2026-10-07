"""Strands @tool wrappers over the Athena service, used by the SQL Agent."""
from __future__ import annotations

from strands import tool

from src.services import athena_service
from src.utils.exceptions import AthenaQueryError, SQLValidationError
from src.utils.logger import get_logger
from src.utils.validators import validate_readonly_sql

logger = get_logger(__name__)


@tool
def run_athena_query(sql: str) -> dict:
    """Execute a read-only SELECT SQL statement against the clinical_db Athena database.

    Args:
        sql: A single Athena-compatible SELECT (or WITH...SELECT) SQL statement
             referencing only clinical_trials, patient_data, trial_sites,
             adverse_events, or study_metrics.

    Returns:
        A dict with keys: columns (list[str]), rows (list[dict]), row_count (int),
        query_execution_id (str). If validation or execution fails, returns a dict
        with an "error" key describing the problem instead of raising.
    """
    try:
        validated_sql = validate_readonly_sql(sql)
    except SQLValidationError as exc:
        logger.warning("SQL validation failed: %s", exc.message)
        return {"error": exc.message, "sql": sql}

    try:
        result = athena_service.run_query(validated_sql)
    except AthenaQueryError as exc:
        logger.error("Athena query failed: %s", exc.message)
        return {"error": exc.message, "sql": validated_sql}

    return {
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": result["row_count"],
        "query_execution_id": result["query_execution_id"],
        "sql": validated_sql,
    }
