"""Static constants that are not environment-configurable."""

class Intent:
    STRUCTURED = "STRUCTURED"
    UNSTRUCTURED = "UNSTRUCTURED"
    HYBRID = "HYBRID"
    ANALYTICAL = "ANALYTICAL"

    ALL = (STRUCTURED, UNSTRUCTURED, HYBRID, ANALYTICAL)


class AgentName:
    ORCHESTRATOR = "orchestrator"
    SQL_AGENT = "sql_agent"
    RAG_AGENT = "rag_agent"
    ANALYST_AGENT = "analyst_agent"


class ExecutionStatus:
    STARTED = "started"
    TOOL_CALL = "tool_call"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


ATHENA_TERMINAL_STATES = ("SUCCEEDED", "FAILED", "CANCELLED")
ATHENA_POLL_INTERVAL_SECONDS = 1.0
ATHENA_MAX_POLL_SECONDS = 60

CODE_INTERPRETER_LANGUAGE = "python"

# Shown to the user whenever any agent fails. Raw error details are logged
# (with the trace_id) but never surfaced in the UI.
INTERNAL_ERROR_MESSAGE = (
    "Sorry, I'm not able to answer this question right now due to an internal "
    "error. Our team has been notified and is looking into it. Please try again "
    "later or rephrase your question."
)
INTERNAL_ERROR_STEP_DETAIL = "An internal error occurred."
