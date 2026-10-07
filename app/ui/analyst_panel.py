"""Displays the Analyst Agent's chart, executive summary, insights, risks,
recommendations, and self-healing execution attempts."""
from __future__ import annotations

from typing import Any

import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

from src.config.constants import INTERNAL_ERROR_STEP_DETAIL
from src.models.agent_io_schemas import AgentStatus
from src.utils.logger import get_logger

logger = get_logger(__name__)


def render_analyst_panel(analyst_response: Any) -> None:
    if not analyst_response:
        st.caption("Analyst Agent was not invoked for this question.")
        return

    data = analyst_response.data
    status = analyst_response.status
    st.markdown(f"**Status:** `{status}`")

    if analyst_response.error or status == AgentStatus.FAILED:
        # Raw error / stderr is logged server-side; never show it to the user.
        st.warning(INTERNAL_ERROR_STEP_DETAIL)
        return

    charts = data.get("charts") or ([data["chart_json"]] if data.get("chart_json") else [])
    if charts:
        _render_charts(charts)

    summary = data.get("executive_summary")
    if summary:
        st.markdown("### Executive Summary")
        st.markdown(summary)

    _render_bullet_section("Key Insights", data.get("key_insights", []))
    _render_bullet_section("Risks", data.get("risks", []))
    _render_bullet_section("Recommendations", data.get("recommendations", []))

    attempts = data.get("attempts", [])
    if attempts:
        with st.expander(f"Self-healing execution log ({len(attempts)} attempt(s))"):
            for attempt in attempts:
                st.markdown(
                    f"**Attempt {attempt.get('attempt_number')}** — "
                    f"{'✅ success' if attempt.get('success') else '❌ failed'}"
                )
                st.code(attempt.get("code", ""), language="python")


def _render_charts(charts: list[dict]) -> None:
    """Render all figures in ONE self-contained iframe.

    st.plotly_chart is avoided: the browser fails to lazy-load Streamlit's
    ~4 MB PlotlyChart chunk (proxy/AV), so plotly.js is embedded inline via
    the websocket instead — once, shared by every figure in the iframe.
    """
    parts: list[str] = []
    total_height = 0
    for chart_json in charts:
        try:
            # skip_invalid tolerates plotly version skew between the sandbox
            # that produced the figure and the plotly installed here.
            fig = pio.from_json(_to_json_str(chart_json), skip_invalid=True)
        except Exception:  # noqa: BLE001
            logger.exception("Could not parse chart JSON")
            continue
        height = int(fig.layout.height or 500)
        _apply_palette(fig)
        fig.update_layout(height=height)
        parts.append(
            fig.to_html(include_plotlyjs=not parts, full_html=False, config={"responsive": True})
        )
        total_height += height + 20

    if not parts:
        st.warning("The chart could not be displayed.")
        return
    components.html("".join(parts), height=total_height, scrolling=False)


# Muted, print-friendly palette matching the app theme.
CHART_COLORS = [
    "#2F6F73", "#D08C3A", "#6B8F4E", "#B5534A", "#5B6C9C",
    "#C2A14D", "#8A6A8F", "#4F9BA0", "#9C7A5B", "#7C8A93",
]


def _apply_palette(fig) -> None:
    """Give the figure explicit colours.

    The sandbox strips the Plotly template (see code_generator.py), so traces
    arrive with no colorway — pies in particular then render solid black.
    """
    fig.update_layout(
        template="plotly_white",
        colorway=CHART_COLORS,
        piecolorway=CHART_COLORS,
        font=dict(family="Source Sans Pro, sans-serif", color="#2B2B2B"),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    for trace in fig.data:
        if trace.type == "pie" and trace.marker.colors is None:
            n = len(trace.labels or trace.values or [])
            trace.marker.colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(n)]
            trace.marker.line = dict(color="#FFFFFF", width=1.5)


def _render_bullet_section(title: str, items: list[str]) -> None:
    if not items:
        return
    st.markdown(f"### {title}")
    for item in items:
        st.markdown(f"- {item}")


def _to_json_str(chart_json: dict) -> str:
    import json

    return json.dumps(chart_json)
