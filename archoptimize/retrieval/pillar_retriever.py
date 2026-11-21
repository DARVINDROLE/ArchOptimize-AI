"""Search the documentation of one pillar (e.g. only Reliability docs for the Reliability
reviewer), so each reviewer gets on-topic evidence. Top-k is small (≈4) to keep prompts short."""

from __future__ import annotations

from functools import lru_cache

from archoptimize.retrieval.text_embedder import Embedder, FastEmbedEmbedder
from archoptimize.retrieval.vector_store import KnowledgeIndex
from archoptimize.schemas.doc_chunk import RetrievedChunk
from archoptimize.schemas.finding import Pillar

DEFAULT_TOP_K = 4


class IndexNotBuiltError(RuntimeError):
    pass


class PillarRetriever:
    def __init__(self, index: KnowledgeIndex, embedder: Embedder):
        self._index = index
        self._embedder = embedder

    def retrieve(
        self, query: str, pillar: Pillar | None = None, k: int = DEFAULT_TOP_K
    ) -> list[RetrievedChunk]:
        return self._index.search(self._embedder.embed_query(query), pillar, k)


@lru_cache(maxsize=1)
def default_retriever() -> PillarRetriever:
    """The shared retriever over the shipped index (loaded once per process)."""
    index = KnowledgeIndex()
    if index.count() == 0:
        raise IndexNotBuiltError(
            "The documentation index is empty. Build it with: "
            "uv run python -m archoptimize.knowledge_base.index_builder"
        )
    return PillarRetriever(index, FastEmbedEmbedder())
