"""S3 helper service — reading/writing artifacts (chart JSON, logs, exports)."""
from __future__ import annotations

import json
from typing import Any

from src.config.aws_config import s3_client
from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.retry import with_retry

logger = get_logger(__name__)


@with_retry(max_attempts=3)
def put_json(key: str, payload: dict[str, Any], bucket: str | None = None) -> str:
    client = s3_client()
    bucket = bucket or settings.data_bucket
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )
    uri = f"s3://{bucket}/{key}"
    logger.info("Wrote artifact to %s", uri)
    return uri


@with_retry(max_attempts=3)
def get_json(key: str, bucket: str | None = None) -> dict[str, Any]:
    client = s3_client()
    bucket = bucket or settings.data_bucket
    obj = client.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


@with_retry(max_attempts=3)
def list_objects(prefix: str, bucket: str | None = None) -> list[str]:
    client = s3_client()
    bucket = bucket or settings.data_bucket
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys
