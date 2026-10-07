"""
Centralized retry decorator for transient infrastructure failures
(throttling, timeouts, connection resets).

This is distinct from the Analyst Agent's self-healing loop, which retries
on *logical* code failures, not infrastructure failures. Do not conflate
the two.
"""
from __future__ import annotations

import functools
import time
from typing import Callable, TypeVar

from botocore.exceptions import ClientError, EndpointConnectionError

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

TRANSIENT_ERROR_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ProvisionedThroughputExceededException",
    "RequestTimeout",
    "InternalServerException",
    "ServiceUnavailableException",
}


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, EndpointConnectionError):
        return True
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in TRANSIENT_ERROR_CODES
    return False


def with_retry(
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
):
    """Retry a function on transient AWS errors with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = base_delay_seconds
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt == max_attempts or not _is_transient(exc):
                        raise
                    logger.warning(
                        "Transient error on attempt %s/%s for %s: %s. Retrying in %.1fs",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= backoff_multiplier
            if last_exc:  # pragma: no cover - defensive
                raise last_exc
            return None  # pragma: no cover

        return wrapper

    return decorator
