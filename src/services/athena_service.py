"""
Athena query execution service.

Owns: starting queries, polling for completion, paginating/parsing results.
Agents/tools never call boto3 Athena directly — they call
`run_query()` from here.
"""
from __future__ import annotations

import time
from typing import Any

from src.config.aws_config import athena_client
from src.config.constants import ATHENA_MAX_POLL_SECONDS, ATHENA_POLL_INTERVAL_SECONDS
from src.config.settings import settings
from src.utils.exceptions import AthenaQueryError, AthenaTimeoutError
from src.utils.logger import get_logger
from src.utils.retry import with_retry

logger = get_logger(__name__)


@with_retry(max_attempts=3)
def _start_query(sql: str) -> str:
    client = athena_client()
    try:
        response = client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": settings.athena_database},
            ResultConfiguration={"OutputLocation": settings.athena_output_location},
            WorkGroup=settings.athena_workgroup,
        )
        return response["QueryExecutionId"]
    except Exception as exc:  # noqa: BLE001
        raise AthenaQueryError(f"Failed to start Athena query: {exc}", context={"sql": sql}) from exc


def _wait_for_completion(query_execution_id: str) -> dict[str, Any]:
    client = athena_client()
    elapsed = 0.0
    while elapsed < ATHENA_MAX_POLL_SECONDS:
        resp = client.get_query_execution(QueryExecutionId=query_execution_id)
        status = resp["QueryExecution"]["Status"]["State"]
        if status == "SUCCEEDED":
            return resp
        if status in ("FAILED", "CANCELLED"):
            reason = resp["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
            raise AthenaQueryError(
                f"Athena query {status.lower()}: {reason}",
                context={"query_execution_id": query_execution_id},
            )
        time.sleep(ATHENA_POLL_INTERVAL_SECONDS)
        elapsed += ATHENA_POLL_INTERVAL_SECONDS

    raise AthenaTimeoutError(
        f"Athena query {query_execution_id} did not complete within "
        f"{ATHENA_MAX_POLL_SECONDS}s.",
        context={"query_execution_id": query_execution_id},
    )


def _parse_results(query_execution_id: str) -> tuple[list[str], list[dict[str, Any]]]:
    client = athena_client()
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    paginator = client.get_paginator("get_query_results")

    for page_index, page in enumerate(paginator.paginate(QueryExecutionId=query_execution_id)):
        result_rows = page["ResultSet"]["Rows"]
        if page_index == 0:
            # First row of the first page is the header row.
            columns = [c.get("VarCharValue", "") for c in result_rows[0]["Data"]]
            data_rows = result_rows[1:]
        else:
            data_rows = result_rows

        for row in data_rows:
            values = [cell.get("VarCharValue") for cell in row["Data"]]
            rows.append(dict(zip(columns, values)))

    return columns, rows


def run_query(sql: str) -> dict[str, Any]:
    """Execute a validated read-only SQL string against Athena and return results.

    Returns:
        {"columns": [...], "rows": [...], "row_count": int, "query_execution_id": str}
    """
    logger.info("Starting Athena query: %s", sql)
    query_execution_id = _start_query(sql)
    _wait_for_completion(query_execution_id)
    columns, rows = _parse_results(query_execution_id)
    logger.info("Athena query %s completed with %d rows.", query_execution_id, len(rows))
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "query_execution_id": query_execution_id,
    }
