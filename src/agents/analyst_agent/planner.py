"""Produces a short analysis plan from the user question + collected context."""
from __future__ import annotations

import json
from typing import Any

from src.services.bedrock_service import invoke_converse_json
from src.prompts.analyst_agent_prompts import PLANNER_SYSTEM_PROMPT
from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_analysis_plan(user_question: str, context_data: dict[str, Any]) -> dict[str, Any]:
    """Return {"plan_steps": [...], "requires_chart": bool, "chart_type": str}."""
    user_prompt = (
        f"User question: {user_question}\n\n"
        f"Available context data (truncated preview):\n"
        f"{json.dumps(context_data, default=str)[:4000]}"
    )
    try:
        plan = invoke_converse_json(PLANNER_SYSTEM_PROMPT, user_prompt, temperature=0.1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Planner failed, falling back to default plan: %s", exc)
        plan = {
            "plan_steps": ["Summarize the available data", "Identify notable patterns"],
            "requires_chart": False,
            "chart_type": "none",
        }
    plan.setdefault("plan_steps", [])
    plan.setdefault("requires_chart", False)
    plan.setdefault("chart_type", "none")
    return plan
