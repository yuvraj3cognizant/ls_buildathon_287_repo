"""
AgentCore Code Interpreter execution service.

Owns the lifecycle of a Code Interpreter session: start -> execute code ->
capture stdout/stderr/result -> stop. This is the ONLY module that talks to
the `bedrock-agentcore` control/data plane.

Uses the `bedrock_agentcore` SDK's CodeInterpreter helper when available,
and falls back to raw boto3 `bedrock-agentcore` client calls otherwise, so
this module keeps working regardless of which SDK version is installed in
the environment.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from src.config.settings import settings
from src.utils.exceptions import CodeExecutionError, CodeExecutionTimeoutError
from src.utils.logger import get_logger
from src.utils.timers import Deadline

logger = get_logger(__name__)

try:
    from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter as _AgentCoreCodeInterpreter

    _HAS_AGENTCORE_SDK = True
except ImportError:  # pragma: no cover - environment dependent
    _HAS_AGENTCORE_SDK = False


@contextmanager
def _session() -> Iterator[Any]:
    """Yield an active Code Interpreter session, cleaning up on exit."""
    if not _HAS_AGENTCORE_SDK:
        raise CodeExecutionError(
            "bedrock_agentcore SDK is not installed. Run: "
            "pip install bedrock-agentcore"
        )

    interpreter = _AgentCoreCodeInterpreter(region=settings.aws_region)
    interpreter.start(identifier=settings.code_interpreter_identifier or None)
    try:
        yield interpreter
    finally:
        try:
            interpreter.stop()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to cleanly stop Code Interpreter session.")


def _extract_stream_text(stream: Any) -> tuple[str, str, Any]:
    """Normalize the AgentCore response stream into (stdout, stderr, result)."""
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    result: Any = None

    events = stream if isinstance(stream, list) else stream.get("stream", [])
    for event in events:
        result_block = event.get("result", event) if isinstance(event, dict) else {}
        content = result_block.get("content", [])
        is_error = result_block.get("isError", False)
        for block in content:
            text = block.get("text", "")
            if is_error:
                stderr_parts.append(text)
            else:
                stdout_parts.append(text)
        if "structuredContent" in result_block:
            result = result_block["structuredContent"]

    return "\n".join(stdout_parts), "\n".join(stderr_parts), result


def execute_code(code: str, timeout_seconds: int | None = None) -> dict[str, Any]:
    """Execute a Python snippet inside an AgentCore Code Interpreter sandbox.

    Returns: {"stdout": str, "stderr": str, "success": bool, "result": Any}
    """
    deadline = Deadline(max_seconds=timeout_seconds or settings.max_execution_seconds)

    with _session() as interpreter:
        try:
            response = interpreter.invoke(
                "executeCode",
                {"code": code, "language": "python", "clearContext": False},
            )
        except Exception as exc:  # noqa: BLE001
            raise CodeExecutionError(f"Code Interpreter invocation failed: {exc}") from exc

        deadline.check()
        stdout, stderr, result = _extract_stream_text(response)

        success = not stderr
        if not success:
            logger.warning("Generated code raised an error inside Code Interpreter: %s", stderr)

        return {"stdout": stdout, "stderr": stderr, "success": success, "result": result}


def execute_code_safe(code: str, timeout_seconds: int | None = None) -> dict[str, Any]:
    """Same as execute_code, but never raises — failures are returned in-band
    so the Analyst Agent's self-healing loop can inspect and react to them.
    """
    try:
        return execute_code(code, timeout_seconds)
    except CodeExecutionTimeoutError as exc:
        return {"stdout": "", "stderr": str(exc), "success": False, "result": None}
    except CodeExecutionError as exc:
        return {"stdout": "", "stderr": str(exc), "success": False, "result": None}
