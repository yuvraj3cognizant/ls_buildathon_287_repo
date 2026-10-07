"""Regression tests for the sandbox result-serialization contract.

These run the injected `_RUNTIME_PREAMBLE` locally (no AWS needed) because
that preamble is what actually decides whether a chart survives the trip
back from the Code Interpreter.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import plotly.express as px
import pytest

from src.agents.analyst_agent.code_generator import (
    _RUNTIME_PREAMBLE,
    build_executable_snippet,
)


@pytest.fixture()
def sandbox_ns() -> dict:
    """The namespace the generated code sees inside the sandbox."""
    ns: dict = {"json": json}
    exec(_RUNTIME_PREAMBLE, ns)  # noqa: S102 - exercising the real preamble
    return ns


def _emit_and_parse(ns: dict, findings, fig=None) -> tuple[dict, dict | None]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        ns["emit_results"](findings, fig)

    parsed_findings, parsed_chart = None, None
    for line in buffer.getvalue().splitlines():
        if line.startswith("FINDINGS_JSON::"):
            parsed_findings = json.loads(line[len("FINDINGS_JSON::"):])
        elif line.startswith("CHART_JSON::"):
            parsed_chart = json.loads(line[len("CHART_JSON::"):])
    return parsed_findings, parsed_chart


def test_chart_axes_survive_as_arrays(sandbox_ns):
    """Regression: json.dumps(fig.to_dict(), default=str) stringified the
    numpy-backed x/y into "['Mild' 'Moderate']", which parsed as valid JSON
    and so broke silently at render time instead of raising."""
    fig = px.bar(
        {"severity": ["Mild", "Moderate", "Severe"], "count": [33, 25, 17]},
        x="severity",
        y="count",
    )
    _, chart = _emit_and_parse(sandbox_ns, {"n": 3}, fig)

    trace = chart["data"][0]
    assert isinstance(trace["x"], list), f"x became {type(trace['x']).__name__}"
    assert isinstance(trace["y"], list), f"y became {type(trace['y']).__name__}"
    assert list(trace["x"]) == ["Mild", "Moderate", "Severe"]
    assert list(trace["y"]) == [33, 25, 17]


def test_version_specific_template_is_stripped(sandbox_ns):
    """The sandbox's plotly template can name trace types the host's plotly
    has removed (e.g. 'heatmapgl'), which makes it reject the whole figure."""
    fig = px.bar({"a": ["x"], "b": [1]}, x="a", y="b")
    _, chart = _emit_and_parse(sandbox_ns, {}, fig)
    assert "template" not in chart.get("layout", {})


def test_findings_keep_native_numeric_types(sandbox_ns):
    """numpy scalars must become real numbers, not strings, so the insight
    generator reasons over numbers."""
    import numpy as np

    findings = {"total": np.int64(75), "mean": np.float64(25.0), "labels": np.array(["a", "b"])}
    parsed, _ = _emit_and_parse(sandbox_ns, findings)

    assert parsed["total"] == 75 and isinstance(parsed["total"], int)
    assert parsed["mean"] == 25.0 and isinstance(parsed["mean"], float)
    assert parsed["labels"] == ["a", "b"]


def test_no_chart_emits_explicit_null(sandbox_ns):
    parsed, chart = _emit_and_parse(sandbox_ns, {"n": 1})
    assert parsed == {"n": 1}
    assert chart is None


def test_snippet_injects_context_and_helper():
    snippet = build_executable_snippet("print('hi')", {"sql": {"rows": []}})
    assert "context_data = json.loads" in snippet
    assert "def emit_results(" in snippet
    assert snippet.endswith("print('hi')")
