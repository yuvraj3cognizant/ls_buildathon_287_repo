"""Centralized Streamlit session_state helpers so panels don't touch
st.session_state keys directly (avoids typos / key drift).

Chats are persisted per user to disk so a user's previous conversations
survive reloads / logouts and can be reopened from the sidebar.
"""
from __future__ import annotations

import pickle
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from src.utils.logger import get_logger

logger = get_logger("session_state")

HISTORY_KEY = "conversation_history"
LAST_RESULT_KEY = "last_orchestrator_result"
CURRENT_AGENT_KEY = "current_processing_agent"
# One entry per completed exchange: {"question", "answer", "result"}. Each turn
# keeps its OWN orchestrator result so per-question panels stay scoped to that
# question instead of every turn re-reading a single shared "last result".
TURNS_KEY = "turns"
# All of the signed-in user's chats: {chat_id: {"id", "title", "created", "turns", "history"}}.
CHATS_KEY = "chats"
ACTIVE_CHAT_KEY = "active_chat_id"
CHATS_OWNER_KEY = "chats_owner"

# Pickle (not JSON) because turn results can hold DataFrames for the panels.
CHAT_STORE_DIR = Path(__file__).resolve().parents[2] / "data" / "chat_history"


def _store_path(username: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", username) or "anonymous"
    return CHAT_STORE_DIR / f"{safe}.pkl"


def _load_chats(username: str) -> dict[str, dict[str, Any]]:
    path = _store_path(username)
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            return pickle.load(fh)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to load chat history for %s", username)
        return {}


def save_chats() -> None:
    username = st.session_state.get(CHATS_OWNER_KEY)
    if not username:
        return
    # Don't persist empty "New chat" placeholders.
    chats = {cid: c for cid, c in st.session_state[CHATS_KEY].items() if c["history"]}
    try:
        CHAT_STORE_DIR.mkdir(parents=True, exist_ok=True)
        with _store_path(username).open("wb") as fh:
            pickle.dump(chats, fh)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save chat history for %s", username)


def _new_chat_record() -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "title": "New chat",
        "created": datetime.now().isoformat(timespec="seconds"),
        "turns": [],
        "history": [],
    }


def _activate(chat_id: str) -> None:
    chat = st.session_state[CHATS_KEY][chat_id]
    st.session_state[ACTIVE_CHAT_KEY] = chat_id
    # Alias the active chat's lists so existing append/get helpers mutate it in place.
    st.session_state[TURNS_KEY] = chat["turns"]
    st.session_state[HISTORY_KEY] = chat["history"]
    st.session_state["session_id"] = chat_id
    st.session_state[LAST_RESULT_KEY] = chat["turns"][-1]["result"] if chat["turns"] else None


def init_session_state(username: str) -> None:
    if st.session_state.get(CHATS_OWNER_KEY) != username:
        # First run for this user (or a different user logged in): load their chats.
        st.session_state[CHATS_OWNER_KEY] = username
        st.session_state[CHATS_KEY] = _load_chats(username)
        st.session_state.pop(ACTIVE_CHAT_KEY, None)
    if st.session_state.get(ACTIVE_CHAT_KEY) not in st.session_state[CHATS_KEY]:
        new_chat()
    if CURRENT_AGENT_KEY not in st.session_state:
        st.session_state[CURRENT_AGENT_KEY] = None


def new_chat() -> None:
    """Start a fresh chat, reusing the current one if it is still empty."""
    active = st.session_state.get(ACTIVE_CHAT_KEY)
    chats = st.session_state[CHATS_KEY]
    if active in chats and not chats[active]["history"]:
        return
    chat = _new_chat_record()
    chats[chat["id"]] = chat
    _activate(chat["id"])


def switch_chat(chat_id: str) -> None:
    if chat_id in st.session_state[CHATS_KEY]:
        _activate(chat_id)


def rename_chat(chat_id: str, title: str) -> None:
    title = title.strip()
    chat = st.session_state[CHATS_KEY].get(chat_id)
    if chat is None or not title:
        return
    chat["title"] = title
    save_chats()


def list_chats() ->list[dict[str, Any]]:
    """Non-empty chats, newest first."""
    chats = [c for c in st.session_state.get(CHATS_KEY, {}).values() if c["history"]]
    return sorted(chats, key=lambda c: c["created"], reverse=True)


def get_active_chat_id() -> str | None:
    return st.session_state.get(ACTIVE_CHAT_KEY)


def append_turn(question: str, result: dict[str, Any]) -> None:
    st.session_state[TURNS_KEY].append(
        {"question": question, "answer": result.get("final_answer", ""), "result": result}
    )
    save_chats()


def get_turns() -> list[dict[str, Any]]:
    return st.session_state.get(TURNS_KEY, [])


def append_message(role: str, content: str) -> None:
    st.session_state[HISTORY_KEY].append({"role": role, "content": content})
    chat = st.session_state[CHATS_KEY].get(st.session_state.get(ACTIVE_CHAT_KEY))
    if chat is not None and role == "user" and chat["title"] == "New chat":
        chat["title"] = content if len(content) <= 50 else content[:50] + "…"
    save_chats()


def get_history() -> list[dict[str, str]]:
    return st.session_state.get(HISTORY_KEY, [])


def set_last_result(result: dict[str, Any]) -> None:
    st.session_state[LAST_RESULT_KEY] = result


def get_last_result() -> dict[str, Any] | None:
    return st.session_state.get(LAST_RESULT_KEY)


def set_current_agent(agent_name: str | None) -> None:
    st.session_state[CURRENT_AGENT_KEY] = agent_name


def get_current_agent() -> str | None:
    return st.session_state.get(CURRENT_AGENT_KEY)
