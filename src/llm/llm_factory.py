"""
Centralized factory for constructing the Strands-compatible Bedrock model.

Every agent obtains its model instance from `get_model()` — never
instantiates a Bedrock model client directly. This is what lets us change
model ID, temperature defaults, or provider in exactly one place.
"""
from __future__ import annotations

from functools import lru_cache

from strands.models import BedrockModel

from src.config.settings import settings


@lru_cache(maxsize=None)
def get_model(temperature: float = 0.1, max_tokens: int = 4096) -> BedrockModel:
    """Return a cached BedrockModel configured for amazon.nova-pro-v1:0.

    A distinct (temperature, max_tokens) pair yields a distinct cached
    instance, so callers needing different sampling behavior (e.g. the
    Analyst Agent's more creative insight generation vs. the SQL Agent's
    deterministic SQL generation) can request it explicitly.
    """
    return BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_deterministic_model() -> BedrockModel:
    """Low-temperature model for SQL generation / classification tasks."""
    return get_model(temperature=0.0, max_tokens=2048)


def get_reasoning_model() -> BedrockModel:
    """Slightly higher temperature model for analysis / narrative generation."""
    return get_model(temperature=0.3, max_tokens=4096)
