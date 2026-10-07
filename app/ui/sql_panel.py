"""Displays the SQL Agent's generated SQL and structured result table."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.config.constants import INTERNAL_ERROR_STEP_DETAIL
from src.models.agent_io_schemas import AgentStatus


def render_sql_panel(sql_response: Any) -> None:
    if not sql_response:
        st.caption("SQL Agent was not invoked for this question.")
        return

    data = sql_response.data
    status = sql_response.status

    st.markdown(f"**Status:** `{status}`")

    result_sets = data.get("result_sets") or []
    if len(result_sets) > 1:
        # Multi-part questions run several queries; show each with its rows.
        for i, rs in enumerate(result_sets, start=1):
            st.markdown(f"**Query {i} ({rs.get('row_count', 0)} rows):**")
            st.code(rs.get("sql") or "", language="sql")
            if rs.get("rows"):
                st.dataframe(
                    pd.DataFrame(rs["rows"], columns=rs.get("columns") or None),
                    use_container_width=True,
                )
        answer = data.get("answer")
        if answer:
            st.markdown("**SQL Agent narrative:**")
            st.markdown(answer)
        return

    generated_sql = data.get("generated_sql")
    if generated_sql:
        st.markdown("**Generated SQL:**")
        st.code(generated_sql, language="sql")
    else:
        st.caption("No SQL was generated.")

    rows = data.get("rows", [])
    columns = data.get("columns", [])
    if rows:
        df = pd.DataFrame(rows, columns=columns if columns else None)
        st.markdown(f"**Results ({data.get('row_count', len(rows))} rows):**")
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No rows returned.")

    if sql_response.error or status == AgentStatus.FAILED:
        # Raw error is logged server-side; never show it to the user.
        st.warning(INTERNAL_ERROR_STEP_DETAIL)
        return

    answer = data.get("answer")
    if answer:
        st.markdown("**SQL Agent narrative:**")
        st.markdown(answer)
