"""Strands @tool wrappers over the Knowledge Base service, used by the RAG Agent."""
from __future__ import annotations

from strands import tool

from src.services import knowledge_base_service
from src.utils.exceptions import KBRetrievalError
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def retrieve_kb_context(query: str, top_k: int = 5) -> dict:
    """Retrieve relevant passages from the clinical trial document Knowledge Base.

    Args:
        query: The natural language question or topic to search for.
        top_k: Number of top passages to retrieve (default 5).

    Returns:
        A dict with key "chunks": a list of {content, source_document, score}.
        Returns {"error": ...} on failure instead of raising.
    """
    try:
        chunks = knowledge_base_service.retrieve(query, top_k=top_k)
    except KBRetrievalError as exc:
        logger.error("Knowledge Base retrieval failed: %s", exc.message)
        return {"error": exc.message, "query": query}

    return {"chunks": chunks, "query": query}
