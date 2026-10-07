"""Generates (and fixes) the Python analysis code executed in the Code Interpreter."""
from __future__ import annotations

import json
import re
from typing import Any

from src.prompts.analyst_agent_prompts import CODE_FIXER_SYSTEM_PROMPT, CODE_GENERATOR_SYSTEM_PROMPT
from src.services.bedrock_service import invoke_converse

CODE_FENCE_PREFIXES = ("```python", "```py", "```")


def _strip_code_fences(code: str) -> str:
    cleaned = code.strip()
    for prefix in CODE_FENCE_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    if cleaned.endswith("```"):
        cleaned = cleaned[: -3]
    return cleaned.strip()


def generate_analysis_code(plan: dict[str, Any], context_data: dict[str, Any]) -> str:
    user_prompt = (
        f"Analysis plan:\n{json.dumps(plan)}\n\n"
        f"context_data will be injected as a Python dict/list with this shape "
        f"(preview, may be truncated):\n{json.dumps(context_data, default=str)[:4000]}"
    )
    raw = invoke_converse(CODE_GENERATOR_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=3000)
    return _strip_code_fences(raw)


def generate_fixed_code(failing_code: str, stderr: str, plan: dict[str, Any]) -> str:
    user_prompt = (
        f"Analysis plan:\n{json.dumps(plan)}\n\n"
        f"Failing code:\n{failing_code}\n\n"
        f"Error / traceback:\n{stderr[:3000]}"
    )
    raw = invoke_converse(CODE_FIXER_SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=3000)
    return _strip_code_fences(raw)


_RUNTIME_PREAMBLE = '''
def _unpack_bdata(obj):
    """Expand plotly >=6's base64 binary array encoding into a plain list.

    plotly 6+ emits numeric arrays as {"dtype": "i1", "bdata": "IRkR"}. That
    is only readable by a plotly of the same era, so it is decoded here to
    keep the payload portable across sandbox/host version skew.
    """
    try:
        import base64 as _b64

        import numpy as _np

        arr = _np.frombuffer(_b64.b64decode(obj["bdata"]), dtype=_np.dtype(obj["dtype"]))
        shape = obj.get("shape")
        if shape:
            arr = arr.reshape([int(dim) for dim in str(shape).split(",")])
        return arr.tolist()
    except Exception:
        return None


def _to_native(obj):
    """Recursively convert numpy/pandas scalars and arrays to JSON-native types."""
    if isinstance(obj, (str, bool, int, float)) or obj is None:
        return obj
    if hasattr(obj, "item") and getattr(obj, "shape", None) == ():
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, dict):
        if "bdata" in obj and "dtype" in obj:
            unpacked = _unpack_bdata(obj)
            if unpacked is not None:
                return unpacked
        return {str(k): _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_native(v) for v in obj]
    return obj


def emit_results(findings=None, fig=None):
    """Print the two marker lines the host parses out of stdout.

    Uses Plotly's own encoder for the figure. Do NOT hand-roll this with
    json.dumps(fig.to_dict(), default=str): that stringifies the numpy arrays
    behind the x/y properties into values like "['Mild' 'Moderate']", which
    parse as valid JSON and so fail silently at render time instead of
    raising something the self-healing loop could repair.
    """
    print("FINDINGS_JSON::" + json.dumps(_to_native(findings or {}), default=str))
    if fig is None:
        print("CHART_JSON::null")
        return
    # `fig` may be one figure or a list of figures; one marker line each.
    figs = fig if isinstance(fig, (list, tuple)) else [fig]
    for one_fig in figs[:3]:
        # Deliberately to_dict() + _to_native(), NOT to_json(): to_json() is
        # version-dependent, and plotly >=6 encodes numeric arrays as base64
        # ({"dtype": ..., "bdata": ...}) which an older host plotly cannot read.
        # _to_native() emits plain lists, which every plotly version accepts.
        spec = _to_native(one_fig.to_dict())
        # Drop the bundled default template. It is large (it dominates the
        # stdout payload) and version-specific: the sandbox's plotly may name
        # trace types the host's plotly has since removed (e.g. 'heatmapgl',
        # dropped in plotly 6), which makes the host reject the whole figure.
        # Styling is reapplied host-side anyway.
        if isinstance(spec.get("layout"), dict):
            spec["layout"].pop("template", None)
        print("CHART_JSON::" + json.dumps(spec, default=str))

'''


# Plain ints/decimals only. Leading-zero values ("007") stay strings so IDs and
# codes aren't mangled.
_NUMERIC_RE = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?$")


def _coerce_numeric_strings(obj: Any) -> Any:
    """Athena returns every cell as a string ("12", "0.19"). Left as-is, the
    generated pandas code fails with `int + str` TypeErrors on aggregation, so
    numeric-looking strings are converted before the data enters the sandbox."""
    if isinstance(obj, str):
        if _NUMERIC_RE.match(obj):
            return float(obj) if any(c in obj for c in ".eE") else int(obj)
        return obj
    if isinstance(obj, dict):
        return {k: _coerce_numeric_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_numeric_strings(v) for v in obj]
    return obj


def build_executable_snippet(generated_code: str, context_data: dict[str, Any]) -> str:
    """Prepend the context_data injection and result-emitting helpers so the
    generated code's assumptions (`context_data` and `emit_results` already
    exist in the namespace) hold true inside the sandbox, which starts with a
    clean namespace each session.

    The payload is base64-encoded before embedding to avoid any quoting /
    escaping issues from special characters in the underlying data.
    """
    import base64

    context_data = _coerce_numeric_strings(context_data)
    encoded = base64.b64encode(json.dumps(context_data, default=str).encode("utf-8")).decode("ascii")
    injected = (
        "import json, base64\n"
        f"context_data = json.loads(base64.b64decode('{encoded}').decode('utf-8'))\n"
    )
    return injected + _RUNTIME_PREAMBLE + generated_code
