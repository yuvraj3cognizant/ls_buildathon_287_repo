"""Sidebar: app name, chat history, and the signed-in user at the bottom.

The execution trace used to live here; it now streams inline in the main
window under each question, so this panel stays a simple navigation rail.
"""
from __future__ import annotations

import streamlit as st

_AGENT_LABELS = {
    "orchestrator": "Orchestrator",
    "sql_agent": "SQL Agent",
    "rag_agent": "RAG Agent",
    "analyst_agent": "Analyst Agent",
}

# Only failures/retries get a marker so they stand out; everything else is plain.
_EVENT_ICONS = {
    "failed": ":red[✕]",
    "agent_failed": ":red[✕]",
    "retrying": ":orange[↻]",
}


def step_line(step: dict) -> str:
    """One rendered execution-trace line. Shared with the main-window
    execution-flow dropdown so both render steps identically."""
    agent = step.get("agent", "unknown")
    event = step.get("event", "")
    detail = step.get("detail", "")
    icon = _EVENT_ICONS.get(event, "–")
    label = _AGENT_LABELS.get(agent, agent)
    event_str = event.replace("_", " ")
    detail_str = detail.get("reasoning", str(detail)) if isinstance(detail, dict) else str(detail)
    if len(detail_str) > 160:
        detail_str = detail_str[:160] + "…"
    return f"{icon} **{label}** · {event_str}  \n<small>{detail_str}</small>"


def render_sidebar(username: str) -> None:
    from app.ui.session_state import (
        get_active_chat_id,
        list_chats,
        new_chat,
        rename_chat,
        switch_chat,
    )

    with st.sidebar:
        st.markdown("### Clinical Trials Assistant")
        st.caption("Ask about trial data and study documents.")

        if st.button("New chat", icon=":material/edit_square:", use_container_width=True, type="primary"):
            new_chat()
            st.rerun()

        st.markdown("<p style='margin:1.2rem 0 0.3rem;font-size:0.8rem;color:#7A746A;"
                    "text-transform:uppercase;letter-spacing:0.06em'>Recent</p>",
                    unsafe_allow_html=True)
        chats = list_chats()
        with st.container(key="chat_list"):
            if not chats:
                st.caption("Your conversations will show up here.")
            else:
                active_id = get_active_chat_id()
                # Newest first; the open chat is shown highlighted (disabled).
                for chat in chats:
                    is_active = chat["id"] == active_id
                    if st.button(
                        chat["title"],
                        key=f"chat_{chat['id']}",
                        use_container_width=True,
                        type="tertiary",
                        disabled=is_active,
                        help=f"{len(chat['turns'])} question(s) · {chat['created'].replace('T', ' ')}",
                    ):
                        switch_chat(chat["id"])
                        st.rerun()

        active = next((c for c in chats if c["id"] == get_active_chat_id()), None)
        if active is not None:
            with st.popover("Rename this chat", icon=":material/edit:", use_container_width=True):
                with st.form(f"rename_{active['id']}", clear_on_submit=False, border=False):
                    new_title = st.text_input("Chat name", value=active["title"], max_chars=80)
                    if st.form_submit_button("Save", use_container_width=True):
                        rename_chat(active["id"], new_title)
                        st.rerun()

        # Pinned to the bottom of the sidebar by .st-key-sidebar_footer in styles.py.
        with st.container(key="sidebar_footer"):
            col_user, col_btn = st.columns([3, 2], vertical_alignment="center")
            col_user.markdown(f":material/account_circle: **{username}**")
            if col_btn.button("Log out", use_container_width=True):
                from app.ui.login import logout

                logout()
