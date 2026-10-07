"""
Life Sciences Agentic AI Platform — Streamlit frontend.

Run with:
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports resolve when this
# file is launched directly via `streamlit run app/streamlit_app.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

# NOTE: `src.agents.*` is deliberately NOT imported at module scope. Importing
# the orchestrator pulls in strands + boto3 + the whole agent/tool tree (several
# seconds), which delayed the first paint on every cold start. It is imported
# lazily inside `get_orchestrator()`, which only runs once a question is asked.
#
# The result panels (sql/rag/analyst) are also imported lazily: they pull in
# pandas, ~4s of the cold-start import cost, and are only reachable once a
# result exists.
from app.ui.session_state import (
    CHATS_KEY,
    append_message,
    get_active_chat_id,
    append_turn,
    get_history,
    get_turns,
    init_session_state,
    set_current_agent,
    set_last_result,
)
from app.ui.login import AUTH_USER_KEY, is_authenticated, render_login_page
from app.ui.sidebar import render_sidebar, step_line
from app.ui.styles import inject_styles
from src.utils.logger import get_logger, new_trace_id

logger = get_logger("streamlit_app")

st.set_page_config(
    page_title="Life Sciences Agentic AI Platform",
    page_icon="🧬",
    layout="wide",
)

# How many prior turns of chat to hand the orchestrator for context.
HISTORY_TURNS = 6


@st.cache_resource(show_spinner=False)
def _build_orchestrator(agent_src_fingerprint: str):
    """Build + cache the Orchestrator across reruns and sessions.

    Imported here rather than at module scope so the page chrome renders
    before the agent stack is loaded.

    `agent_src_fingerprint` is part of the cache key only. st.cache_resource
    hashes the decorated function's own code, which never changes here, so
    editing anything under src/agents/ would otherwise keep serving an
    instance of the OLD class definition until the server was restarted —
    producing confusing "unexpected keyword argument" style errors.
    """
    del agent_src_fingerprint  # key material, not used in the body
    from src.agents.orchestrator.orchestrator_agent import OrchestratorAgent

    return OrchestratorAgent()


def _agent_src_fingerprint() -> str:
    """Cheap mtime fingerprint of the agent source tree."""
    agents_dir = PROJECT_ROOT / "src" / "agents"
    try:
        return str(max(p.stat().st_mtime_ns for p in agents_dir.rglob("*.py")))
    except ValueError:
        return "empty"


def get_orchestrator():
    return _build_orchestrator(_agent_src_fingerprint())


def _render_detail_tabs(result: dict) -> None:
    """Charts / Data / Sources / Routing tabs for a SINGLE turn's result.

    The final answer itself is already shown above the tabs, so it isn't repeated here.
    """
    from app.ui.analyst_panel import render_analyst_panel
    from app.ui.rag_panel import render_rag_panel
    from app.ui.sql_panel import render_sql_panel

    tab_analyst, tab_sql, tab_rag, tab_routing = st.tabs(
        ["Charts & insights", "Data & query", "Sources", "How I routed this"]
    )
    with tab_routing:
        st.caption("How the question was classified before being handed to the agents.")
        st.json(result.get("intent", {}), expanded=False)
    with tab_sql:
        render_sql_panel(result.get("sql_response"))
    with tab_rag:
        render_rag_panel(result.get("rag_response"))
    with tab_analyst:
        render_analyst_panel(result.get("analyst_response"))


def _render_turn(turn: dict, index: int, is_latest: bool) -> None:
    """One completed exchange: question, its execution flow, its answer, and
    its own detail tabs — all scoped to this turn so earlier turns keep their
    data instead of being overwritten by the newest question."""
    result = turn["result"]

    with st.chat_message("user"):
        st.markdown(turn["question"])

    with st.chat_message("assistant"):
        st.markdown(turn["answer"])

        with st.expander("Show my working", icon=":material/account_tree:", expanded=False):
            for step in result.get("execution_trace") or []:
                st.markdown(step_line(step), unsafe_allow_html=True)

        with st.expander("Details for this answer", icon=":material/table_chart:", expanded=is_latest):
            _render_detail_tabs(result)


def main() -> None:
    inject_styles()

    if not is_authenticated():
        render_login_page()
        return

    username = st.session_state.get(AUTH_USER_KEY, "Analyst")
    init_session_state(username)
    render_sidebar(username=username)

    turns = get_turns()

    if turns:
        st.markdown(f"## {st.session_state[CHATS_KEY][get_active_chat_id()]['title']}")
    else:
        first_name = username.split(".")[0].split("@")[0].capitalize()
        st.markdown(f"# Good to see you, {first_name}.")
        st.markdown(
            "Ask me anything about your clinical trials — enrolment, sites, adverse events, "
            "or what the protocol documents say. I'll pull the numbers and the sources for you."
        )
        st.caption(
            "For example: *How many trials are currently active?* · "
            "*Which sites have the highest dropout rate?* · *Summarise the inclusion criteria for the oncology study.*"
        )

    for i, turn in enumerate(turns, start=1):
        _render_turn(turn, i, is_latest=(i == len(turns)))

    question = st.chat_input("Ask a question about your clinical trial data or documents…")

    if question:
        from src.models.agent_io_schemas import AgentRequest

        append_message("user", question)
        with st.chat_message("user"):
            st.markdown(question)

        session_id = st.session_state.get("session_id", "streamlit-session")
        trace_id = new_trace_id()
        prior_history = get_history()[:-1][-HISTORY_TURNS:]
        request = AgentRequest(
            session_id=session_id,
            user_question=question,
            conversation_history=prior_history,
            trace_id=trace_id,
        )

        with st.chat_message("assistant"):
            # Stream the trace live: the orchestrator calls back on every step,
            # so the user sees routing progress instead of a blank spinner.
            with st.status("Looking into that…", expanded=True) as status:

                def on_step(step: dict) -> None:
                    st.markdown(step_line(step), unsafe_allow_html=True)

                try:
                    orchestrator = get_orchestrator()
                    result = orchestrator.run(request, on_step=on_step)
                except Exception:  # noqa: BLE001
                    logger.exception("Orchestrator run failed (trace_id=%s)", trace_id)
                    from src.config.constants import INTERNAL_ERROR_MESSAGE

                    status.update(label="Something went wrong", state="error")
                    st.markdown(INTERNAL_ERROR_MESSAGE)
                    append_message("assistant", INTERNAL_ERROR_MESSAGE)
                    return
                if result.get("internal_error"):
                    status.update(label="Finished, with a problem", state="error", expanded=False)
                else:
                    status.update(label="Done", state="complete", expanded=False)

        set_last_result(result)
        set_current_agent(None)
        append_message("assistant", result["final_answer"])
        append_turn(question, result)
        # Repaint so this turn renders through the normal per-turn path (with
        # its own collapsed execution flow + detail tabs).
        st.rerun()


if __name__ == "__main__":
    main()
