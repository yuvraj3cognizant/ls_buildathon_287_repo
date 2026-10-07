"""
Read-only smoke check for each AWS boundary the platform depends on.

Exercises the service layer (not raw boto3) so a pass here means the app's
own code paths work. Creates no AWS resources; the only writes are Athena's
own result files in the configured output location.

    python scripts/check_services.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

results: list[tuple[str, bool, str]] = []


def check(label: str, fn) -> None:
    try:
        detail = fn()
        results.append((label, True, detail))
        print(f"[ OK ] {label}: {detail}")
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        results.append((label, False, msg))
        print(f"[FAIL] {label}: {msg[:400]}")


def check_settings() -> str:
    from src.config.settings import settings

    missing = [
        n
        for n, v in (
            ("KNOWLEDGE_BASE_ID", settings.knowledge_base_id),
            ("CODE_INTERPRETER_IDENTIFIER", settings.code_interpreter_identifier),
        )
        if not v or v.startswith("REPLACE_WITH")
    ]
    if missing:
        raise EnvironmentError(f"not set in .env: {', '.join(missing)}")
    return f"region={settings.aws_region} model={settings.bedrock_model_id}"


def check_bedrock() -> str:
    from src.services.bedrock_service import invoke_converse

    out = invoke_converse("Reply with exactly: PONG", "ping", temperature=0.0, max_tokens=10)
    return f"model replied {out.strip()[:40]!r}"


def check_athena() -> str:
    from src.services.athena_service import run_query

    out = run_query("SELECT COUNT(*) AS n FROM clinical_trials")
    return f"{out.get('row_count')} row(s), columns={out.get('columns')}"


def check_knowledge_base() -> str:
    from src.services.knowledge_base_service import retrieve

    chunks = retrieve("clinical trial safety monitoring", top_k=3)
    if not chunks:
        return "reachable but returned 0 chunks (check KB data source sync)"
    return f"{len(chunks)} chunk(s), top score={chunks[0].get('score')}"


def check_code_interpreter() -> str:
    """Runs the same contract the Analyst Agent relies on: inline-injected
    data, pandas + plotly available, results returned via marker lines."""
    from src.agents.analyst_agent.code_generator import build_executable_snippet
    from src.services.code_interpreter_service import execute_code

    code = (
        "import pandas as pd, plotly.express as px, json\n"
        "df = pd.DataFrame(context_data)\n"
        "fig = px.bar(df, x='site', y='dropouts')\n"
        "chart_json = fig.to_dict()\n"
        "findings = {'total_dropouts': int(df['dropouts'].sum())}\n"
        'print("FINDINGS_JSON::" + json.dumps(findings, default=str))\n'
        'print("CHART_JSON::" + json.dumps(chart_json, default=str))\n'
    )
    context = [{"site": "S1", "dropouts": 4}, {"site": "S2", "dropouts": 7}]
    outcome = execute_code(build_executable_snippet(code, context), timeout_seconds=90)

    if not outcome["success"]:
        raise RuntimeError(f"sandbox stderr: {outcome['stderr'][:300]}")

    lines = outcome["stdout"].splitlines()
    got = [m for m in ("FINDINGS_JSON::", "CHART_JSON::") if any(l.startswith(m) for l in lines)]
    if len(got) != 2:
        raise RuntimeError(f"missing marker lines; stdout={outcome['stdout'][:300]!r}")
    return "pandas + plotly ran, both marker lines returned"


if __name__ == "__main__":
    check("settings/.env", check_settings)
    check("Bedrock (Nova)", check_bedrock)
    check("Athena (clinical_db)", check_athena)
    check("Knowledge Base", check_knowledge_base)
    check("AgentCore Code Interpreter", check_code_interpreter)

    failed = [label for label, ok, _ in results if not ok]
    print("\n" + ("All checks passed." if not failed else f"FAILED: {', '.join(failed)}"))
    sys.exit(1 if failed else 0)
