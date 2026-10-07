"""
Centralized boto3 client/session construction.

All services obtain their AWS clients through this module so that region,
retry config, and credential resolution live in exactly one place.
"""
from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from src.config.settings import settings

_BOTO_CONFIG = Config(
    region_name=settings.aws_region,
    retries={"max_attempts": 5, "mode": "adaptive"},
)


@lru_cache(maxsize=None)
def get_session() -> boto3.Session:
    return boto3.Session(region_name=settings.aws_region)


@lru_cache(maxsize=None)
def get_client(service_name: str):
    """Return a cached, correctly-configured boto3 client for a given service."""
    return get_session().client(service_name, config=_BOTO_CONFIG)


# Convenience accessors -------------------------------------------------

def athena_client():
    return get_client("athena")


def s3_client():
    return get_client("s3")


def bedrock_runtime_client():
    return get_client("bedrock-runtime")


def bedrock_agent_runtime_client():
    """Used for Knowledge Base Retrieve / RetrieveAndGenerate calls."""
    return get_client("bedrock-agent-runtime")


def bedrock_agentcore_client():
    """Used for AgentCore Code Interpreter sessions."""
    return get_client("bedrock-agentcore")
