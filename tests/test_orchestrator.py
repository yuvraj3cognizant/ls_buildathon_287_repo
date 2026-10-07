from unittest.mock import patch

from src.agents.orchestrator.intent_classifier import classify_intent
from src.config.constants import Intent


@patch("src.agents.orchestrator.intent_classifier.invoke_converse_json")
def test_structured_intent(mock_invoke):
    mock_invoke.return_value = {
        "intent": Intent.STRUCTURED,
        "requires_sql": True,
        "requires_rag": False,
        "reasoning": "Purely counting patients.",
    }
    result = classify_intent("How many patients dropped out of Trial 001?")
    assert result["intent"] == Intent.STRUCTURED
    assert result["requires_sql"] is True
    assert result["requires_rag"] is False


@patch("src.agents.orchestrator.intent_classifier.invoke_converse_json")
def test_fallback_on_error(mock_invoke):
    mock_invoke.side_effect = RuntimeError("boom")
    result = classify_intent("anything")
    assert result["intent"] == Intent.HYBRID


@patch("src.agents.orchestrator.intent_classifier.invoke_converse_json")
def test_hybrid_question_asking_for_chart_still_runs_analyst(mock_invoke):
    """Regression: a HYBRID question that also asks for a chart must set
    requires_analysis, or the Orchestrator silently skips the Analyst Agent."""
    mock_invoke.return_value = {
        "intent": Intent.HYBRID,
        "requires_sql": True,
        "requires_rag": True,
        "requires_analysis": False,  # model drops the flag
        "reasoning": "Needs both sources.",
    }
    result = classify_intent(
        "Compare adverse event rates across trials with what the safety reviews say, and chart it."
    )
    assert result["requires_analysis"] is True
    assert result["requires_sql"] is True
    assert result["requires_rag"] is True


@patch("src.agents.orchestrator.intent_classifier.invoke_converse_json")
def test_hybrid_forces_both_data_sources(mock_invoke):
    """A HYBRID label with a dropped requires_rag must not starve the RAG Agent."""
    mock_invoke.return_value = {
        "intent": Intent.HYBRID,
        "requires_sql": True,
        "requires_rag": False,
        "reasoning": "Inconsistent model output.",
    }
    result = classify_intent("dropout rates and what the reports say")
    assert result["requires_sql"] is True
    assert result["requires_rag"] is True


@patch("src.agents.orchestrator.intent_classifier.invoke_converse_json")
def test_no_data_source_falls_back_to_intent_defaults(mock_invoke):
    mock_invoke.return_value = {
        "intent": Intent.STRUCTURED,
        "requires_sql": False,
        "requires_rag": False,
        "reasoning": "Degenerate output.",
    }
    result = classify_intent("how many patients")
    assert result["requires_sql"] or result["requires_rag"]
