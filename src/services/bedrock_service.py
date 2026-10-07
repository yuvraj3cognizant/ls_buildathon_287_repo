"""
Centralized Bedrock invocation.

All *direct* (non-Strands-agent) Bedrock calls — e.g. the Orchestrator's
intent classification, or one-off structured-JSON generation — go through
this module so retry/logging/error-translation is not duplicated.

Agent reasoning that goes through Strands `Agent.__call__` does NOT need
this module (Strands + llm_factory handle that path); this module is for
direct `converse` calls used by lightweight helper LLM calls.
"""
from __future__ import annotations

import json

from src.config.aws_config import bedrock_runtime_client
from src.config.settings import settings
from src.utils.exceptions import BedrockInvocationError
from src.utils.logger import get_logger
from src.utils.retry import with_retry

logger = get_logger(__name__)


@with_retry(max_attempts=3)
def invoke_converse(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """Call Bedrock Converse API and return the text response."""
    client = bedrock_runtime_client()
    try:
        response = client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
        )
        content_blocks = response["output"]["message"]["content"]
        return "".join(block.get("text", "") for block in content_blocks)
    except Exception as exc:  # noqa: BLE001
        logger.error("Bedrock invocation failed: %s", exc)
        raise BedrockInvocationError(f"Bedrock invocation failed: {exc}") from exc


def invoke_converse_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> dict:
    """Call Bedrock and parse the response as JSON.

    The system prompt passed in MUST instruct the model to return only raw
    JSON with no markdown fences or preamble.
    """
    raw = invoke_converse(system_prompt, user_prompt, temperature, max_tokens)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Bedrock JSON response: %s | raw=%s", exc, raw)
        raise BedrockInvocationError(
            f"Model did not return valid JSON: {exc}", context={"raw_response": raw}
        ) from exc
