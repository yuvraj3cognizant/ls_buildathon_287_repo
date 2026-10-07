"""Custom exception hierarchy.

Service-layer code must catch raw boto3/botocore exceptions and re-raise as
one of these, so agents never need to know about AWS SDK internals.
"""


class AgentPlatformError(Exception):
    """Base class for all platform errors."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}


class AthenaQueryError(AgentPlatformError):
    pass


class AthenaTimeoutError(AthenaQueryError):
    pass


class KBRetrievalError(AgentPlatformError):
    pass


class BedrockInvocationError(AgentPlatformError):
    pass


class CodeExecutionError(AgentPlatformError):
    """Raised when generated Python code fails inside the Code Interpreter."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "", context: dict | None = None):
        super().__init__(message, context=context)
        self.stdout = stdout
        self.stderr = stderr


class CodeExecutionTimeoutError(CodeExecutionError):
    pass


class IntentClassificationError(AgentPlatformError):
    pass


class SQLValidationError(AgentPlatformError):
    pass


class OrchestrationError(AgentPlatformError):
    pass
