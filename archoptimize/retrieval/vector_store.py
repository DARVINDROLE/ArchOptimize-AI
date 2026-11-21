"""The knowledge index on disk (Chroma). Stores chunk text + metadata + embedding.

We compute embeddings ourselves (text_embedder) and give Chroma plain vectors, so Chroma
never downloads its own embedding model.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import chromadb
from chromadb.config import Settings

from archoptimize.schemas.doc_chunk import DocChunk, RetrievedChunk
from archoptimize.schemas.finding import Pillar

DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge_index"
COLLECTION_NAME = "aws_docs"


class KnowledgeIndex:
    def __init__(self, index_dir: Path = DEFAULT_INDEX_DIR):
        self._client = chromadb.PersistentClient(
            path=str(index_dir), settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_or_create_collection(
            COLLECTION_NAME, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            COLLECTION_NAME, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def add(self, chunks: Sequence[DocChunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings differ in length")
        batch = 1000  # Chroma limits batch sizes
        for start in range(0, len(chunks), batch):
            part = chunks[start : start + batch]
            self._collection.add(
                ids=[c.chunk_id for c in part],
                documents=[c.text for c in part],
                embeddings=[list(e) for e in embeddings[start : start + batch]],
                metadatas=[
                    {
                        "pillar": c.pillar.value,
                        "doc_title": c.doc_title,
                        "page": c.page,
                        "url": c.url,
                    }
                    for c in part
                ],
            )

    def search(
        self, query_embedding: Sequence[float], pillar: Pillar | None, k: int
    ) -> list[RetrievedChunk]:
        result = self._collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=k,
            where={"pillar": pillar.value} if pillar else None,
            include=["documents", "metadatas", "distances"],
        )
        out: list[RetrievedChunk] = []
        for cid, text, meta, dist in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
            strict=True,
        ):
            chunk = DocChunk(
                chunk_id=cid,
                pillar=Pillar(meta["pillar"]),
                doc_title=str(meta["doc_title"]),
                page=int(meta["page"]),
                url=str(meta["url"]),
                text=text,
            )
            out.append(RetrievedChunk(chunk=chunk, score=round(1.0 - float(dist), 4)))
        return out
