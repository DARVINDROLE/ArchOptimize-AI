"""Clean pages → small overlapping chunks with metadata.

Why chunk? Retrieval returns a few passages to put in the prompt. Small chunks keep the
prompt short (important for Groq's free-tier token limits) and precise; a small overlap
stops a sentence that crosses a boundary from being lost.

Size: ~1,200 characters ≈ 300 tokens (smaller than the planned ~500 tokens so that
several chunks per pillar fit in one Groq request).
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from archoptimize.knowledge_base.doc_cleaner import PageText
from archoptimize.knowledge_base.knowledge_sources import KnowledgeSource
from archoptimize.schemas.doc_chunk import DocChunk

CHUNK_CHARS = 1200
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 150

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_CHARS,
    chunk_overlap=OVERLAP_CHARS,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_pages(source: KnowledgeSource, pages: list[PageText]) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    for page in pages:
        for piece in _splitter.split_text(page.text):
            piece = piece.strip()
            if len(piece) < MIN_CHUNK_CHARS:
                continue
            chunks.append(
                DocChunk(
                    chunk_id=f"{source.id_prefix}-{len(chunks):04d}",
                    pillar=source.pillar,
                    doc_title=source.title,
                    page=page.page,
                    url=f"{source.url}#page={page.page}",
                    text=piece,
                )
            )
    return chunks
