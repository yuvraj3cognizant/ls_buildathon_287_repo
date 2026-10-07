"""
Centralized application settings.

Every AWS resource name / ID / model ID used anywhere in the codebase MUST be
read from this module (via `settings`) and never hardcoded elsewhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set.")
    return value or ""


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    # AWS
    aws_region: str = field(default_factory=lambda: _get("AWS_REGION", "us-east-1"))

    # Bedrock
    bedrock_model_id: str = field(
        default_factory=lambda: _get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    )

    # Athena
    athena_database: str = field(default_factory=lambda: _get("ATHENA_DATABASE", "clinical_db"))
    athena_output_location: str = field(
        default_factory=lambda: _get(
            "ATHENA_OUTPUT_LOCATION", "s3://287-my-clinical-data/athena_results/"
        )
    )
    athena_workgroup: str = field(default_factory=lambda: _get("ATHENA_WORKGROUP", "primary"))

    # S3
    data_bucket: str = field(default_factory=lambda: _get("DATA_BUCKET", "287-my-clinical-data"))

    # Bedrock Knowledge Base
    knowledge_base_id: str = field(default_factory=lambda: _get("KNOWLEDGE_BASE_ID", ""))
    knowledge_base_name: str = field(
        default_factory=lambda: _get("KNOWLEDGE_BASE_NAME", "287-knowledge-base-rag")
    )

    # AgentCore Code Interpreter
    code_interpreter_identifier: str = field(
        default_factory=lambda: _get("CODE_INTERPRETER_IDENTIFIER", "")
    )

    # App behavior
    log_level: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO"))
    max_analyst_retries: int = field(default_factory=lambda: _get_int("MAX_ANALYST_RETRIES", 3))
    max_execution_seconds: int = field(
        default_factory=lambda: _get_int("MAX_EXECUTION_SECONDS", 120)
    )


settings = Settings()
