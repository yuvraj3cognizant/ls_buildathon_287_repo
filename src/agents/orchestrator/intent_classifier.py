"""Classifies user intent to decide which specialist agent(s) to invoke."""
from __future__ import annotations

from src.config.constants import Intent
from src.prompts.orchestrator_prompts import INTENT_CLASSIFIER_SYSTEM_PROMPT
from src.services.bedrock_service import invoke_converse_json
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Strong lexical signals that the user wants computed analysis or a chart.
# Used as a safety net: the Analyst Agent is the most visible capability, so
# silently skipping it because the classifier picked a non-ANALYTICAL label
# is far worse than occasionally running it when it wasn't needed.
_ANALYSIS_KEYWORDS = (
    "chart",
    "graph",
    "plot",
    "visuali",
    "trend",
    "analyz",
    "analys",
    "insight",
    "recommend",
    "forecast",
    "correlat",
    "distribution",
    "risk assessment",
    "kri",
)


# Phrases naming something DEFINED IN A DOCUMENT that a query would then have
# to filter on. Paired with a counting/selecting verb below, this is the
# signature of a RAG-then-SQL dependency.
_DOC_DEFINED_TERMS = (
    "inclusion criteria",
    "exclusion criteria",
    "eligibility",
    "criteria",
    "protocol",
    "threshold",
    "definition",
    "endpoint",
    "per the protocol",
    "amendment",
)

_QUANTIFYING_TERMS = (
    "how many",
    "count",
    "number of",
    "which patients",
    "which sites",
    "list the",
    "fall under",
    "meet",
    "qualify",
    "satisfy",
    "comply",
)


def _looks_analytical(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in _ANALYSIS_KEYWORDS)


def _looks_rag_then_sql(question: str) -> bool:
    """Safety net for the model missing the ordering dependency.

    Getting this wrong is expensive: SQL runs in parallel without the criteria
    it needs, silently answers a different question, and the user gets a
    confident wrong count.
    """
    lowered = question.lower()
    return any(t in lowered for t in _DOC_DEFINED_TERMS) and any(
        t in lowered for t in _QUANTIFYING_TERMS
    )


def classify_intent(user_question: str) -> dict:
    """Returns {"intent", "requires_sql", "requires_rag", "requires_analysis", "reasoning"}.

    `intent` says which data sources are needed; `requires_analysis` is an
    orthogonal flag for whether the Analyst Agent should run. They are
    deliberately independent — a HYBRID question can also want a chart, and
    conflating the two is what previously caused the Analyst Agent to be
    skipped for multi-intent questions.
    """
    try:
        result = invoke_converse_json(
            INTENT_CLASSIFIER_SYSTEM_PROMPT, user_question, temperature=0.0
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Intent classification failed, defaulting to HYBRID: %s", exc)
        return {
            "intent": Intent.HYBRID,
            "requires_sql": True,
            "requires_rag": True,
            "requires_analysis": _looks_analytical(user_question),
            "sql_depends_on_rag": _looks_rag_then_sql(user_question),
            "reasoning": "Fallback due to classification error.",
        }

    intent = result.get("intent")
    if isinstance(intent, str):
        intent = intent.strip().upper()
    if intent not in Intent.ALL:
        # Degrade to HYBRID rather than raising. An unrecognized label is a
        # model formatting slip, not a reason to fail the user's whole
        # question — HYBRID simply runs both data agents.
        logger.warning("Model returned unknown intent %r; defaulting to HYBRID.", result.get("intent"))
        intent = Intent.HYBRID

    sql_default = intent in (Intent.STRUCTURED, Intent.HYBRID, Intent.ANALYTICAL)
    rag_default = intent in (Intent.UNSTRUCTURED, Intent.HYBRID, Intent.ANALYTICAL)

    requires_sql = bool(result.get("requires_sql", sql_default))
    requires_rag = bool(result.get("requires_rag", rag_default))
    requires_analysis = bool(result.get("requires_analysis", False)) or _looks_analytical(
        user_question
    )

    # Enforce the invariants in code rather than trusting the model to honor
    # them; a dropped flag here means an agent silently never runs.
    if intent == Intent.HYBRID:
        requires_sql = True
        requires_rag = True
    if intent == Intent.ANALYTICAL:
        requires_analysis = True
    if not (requires_sql or requires_rag):
        logger.warning("Classifier requested no data source for %r; using intent defaults.", user_question)
        requires_sql, requires_rag = sql_default, rag_default
        if not (requires_sql or requires_rag):
            requires_sql = True

    # Ordering dependency: trust the model, but the lexical net can only ever
    # turn it ON — never off — since a missed dependency is the failure mode
    # that produces a wrong count.
    sql_depends_on_rag = bool(result.get("sql_depends_on_rag", False)) or _looks_rag_then_sql(
        user_question
    )
    # Meaningless unless both agents actually run.
    sql_depends_on_rag = sql_depends_on_rag and requires_sql and requires_rag

    result.update(
        {
            "intent": intent,
            "requires_sql": requires_sql,
            "requires_rag": requires_rag,
            "requires_analysis": requires_analysis,
            "sql_depends_on_rag": sql_depends_on_rag,
        }
    )
    return result
