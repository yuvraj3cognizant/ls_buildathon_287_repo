"""
Extraction of tool-call payloads from a Strands agent's message history.

Strands puts a `@tool`'s return value into a `toolResult` content block, but
the exact shape is version-dependent: some versions emit
`{"json": {...}}` while strands-agents >=1.x serializes the dict to
`{"text": "<json string>"}`. Both are handled here so agents don't have to
care, and so a future SDK change only needs fixing in one place.
"""
from __future__ import annotations

import json
from typing import Any


def extract_tool_payloads(agent: Any, *, since_index: int = 0) -> list[dict[str, Any]]:
    """Return every dict payload returned by a tool, in call order.

    `since_index` should be the value of `len(agent.messages)` captured
    immediately *before* the current invocation. Strands agents accumulate
    conversation history across calls, so without this the caller would also
    pick up tool results from earlier, unrelated questions.
    """
    payloads: list[dict[str, Any]] = []

    for message in (getattr(agent, "messages", None) or [])[since_index:]:
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            tool_result = block.get("toolResult")
            if not isinstance(tool_result, dict):
                continue
            for item in tool_result.get("content") or []:
                payload = _coerce_payload(item)
                if payload is not None:
                    payloads.append(payload)

    return payloads


def _coerce_payload(item: Any) -> dict[str, Any] | None:
    """Normalize one tool-result content item into a dict, or None."""
    if not isinstance(item, dict):
        return None

    direct = item.get("json")
    if isinstance(direct, dict):
        return direct

    text = item.get("text")
    if isinstance(text, str) and text.strip().startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed

    return None
