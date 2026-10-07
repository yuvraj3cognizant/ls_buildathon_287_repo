"""
Bedrock Knowledge Base retrieval service.

Owns all calls to bedrock-agent-runtime (Retrieve / RetrieveAndGenerate)
against the `287-knowledge-base-rag` Knowledge Base.
"""
from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from src.config.aws_config import bedrock_agent_runtime_client
from src.config.settings import settings
from src.utils.exceptions import KBRetrievalError
from src.utils.logger import get_logger
from src.utils.retry import with_retry

logger = get_logger(__name__)


def _search_configs(top_k: int) -> list[dict[str, Any]]:
    """Retrieve request shapes to try, in order.

    Bedrock has two mutually exclusive shapes: *managed* knowledge bases
    (AWS-hosted vector store) require `managedSearchConfiguration` and reject
    `vectorSearchConfiguration` with a ValidationException, while
    customer-managed vector stores require the opposite. We try managed first
    and fall back, so the same code works against either KB type.
    """
    return [
        {"managedSearchConfiguration": {"numberOfResults": top_k}},
        {"vectorSearchConfiguration": {"numberOfResults": top_k}},
    ]


def _source_label(result: dict[str, Any]) -> str:
    """Build a human-readable citation for a retrieved chunk.

    Prefers the KB-supplied document title plus page number over the raw
    (URL-encoded) S3 URI, since the URI renders poorly in the UI.
    """
    metadata = result.get("metadata") or {}
    title = metadata.get("_document_title")
    if not title:
        location = result.get("location") or {}
        uri = (location.get("s3Location") or {}).get("uri") or result.get("documentId")
        title = str(uri).rsplit("/", 1)[-1] if uri else location.get("type", "unknown")

    page = metadata.get("_excerpt_page_number")
    if page is not None:
        try:
            return f"{title} (p. {int(float(page))})"
        except (TypeError, ValueError):
            pass
    return str(title)


@with_retry(max_attempts=3)
def retrieve(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Retrieve top-k relevant chunks from the Knowledge Base for a query."""
    client = bedrock_agent_runtime_client()

    configs = _search_configs(top_k)
    response = None
    last_exc: Exception | None = None
    for config in configs:
        try:
            response = client.retrieve(
                knowledgeBaseId=settings.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=config,
            )
            break
        except ClientError as exc:
            last_exc = exc
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "ValidationException":
                break  # a real failure (auth, missing KB) — don't mask it
            logger.debug("Retrieve config %s rejected, trying next.", next(iter(config)))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            break

    if response is None:
        raise KBRetrievalError(
            f"Knowledge Base retrieve failed: {last_exc}", context={"query": query}
        ) from last_exc

    chunks = []
    for result in response.get("retrievalResults", []):
        chunks.append(
            {
                "content": result.get("content", {}).get("text", ""),
                "source_document": _source_label(result),
                "score": result.get("score"),
                "location": str(result.get("location", {})),
            }
        )
    return chunks


@with_retry(max_attempts=3)
def retrieve_and_generate(query: str) -> dict[str, Any]:
    """Use Bedrock's managed RetrieveAndGenerate for a grounded answer + citations."""
    client = bedrock_agent_runtime_client()
    try:
        response = client.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": settings.knowledge_base_id,
                    "modelArn": settings.bedrock_model_id,
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise KBRetrievalError(
            f"Knowledge Base retrieve_and_generate failed: {exc}", context={"query": query}
        ) from exc

    answer = response.get("output", {}).get("text", "")
    citations = response.get("citations", [])
    sources = []
    for citation in citations:
        for ref in citation.get("retrievedReferences", []):
            uri = ref.get("location", {}).get("s3Location", {}).get("uri")
            if uri:
                sources.append(uri)

    return {"answer": answer, "sources": list(dict.fromkeys(sources)), "raw_citations": citations}
