"""Displays the RAG Agent's retrieved document sources and chunks."""
from __future__ import annotations

from typing import Any

import streamlit as st

from src.config.constants import INTERNAL_ERROR_STEP_DETAIL
from src.models.agent_io_schemas import AgentStatus


def render_rag_panel(rag_response: Any) -> None:
    if not rag_response:
        st.caption("RAG Agent was not invoked for this question.")
        return

    data = rag_response.data
    status = rag_response.status

    st.markdown(f"**Status:** `{status}`")

    sources = data.get("sources", [])
    if sources:
        st.markdown("**Retrieved Document Sources:**")
        for src in sources:
            st.markdown(f"- `{src}`")
    else:
        st.caption("No sources retrieved.")

    chunks = data.get("chunks", [])
    if chunks:
        st.markdown(f"**Retrieved Chunks ({len(chunks)}):**")
        for i, chunk in enumerate(chunks, start=1):
            score = chunk.get("score")
            score_str = f" · score {score:.3f}" if isinstance(score, (int, float)) else ""
            with st.expander(f"Chunk {i} — {chunk.get('source_document', 'unknown')}{score_str}"):
                st.write(chunk.get("content", ""))

    if rag_response.error or status == AgentStatus.FAILED:
        # Raw error is logged server-side; never show it to the user.
        st.warning(INTERNAL_ERROR_STEP_DETAIL)
        return

    answer = data.get("answer")
    if answer:
        st.markdown("**RAG Agent grounded answer:**")
        st.markdown(answer)
