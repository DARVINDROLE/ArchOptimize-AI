"""Build the documentation index: download → clean → chunk → embed → store.

uv run python -m archoptimize.knowledge_base.index_builder            # build (reuses downloads)
uv run python -m archoptimize.knowledge_base.index_builder --redownload
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from archoptimize.knowledge_base.doc_chunker import chunk_pages
from archoptimize.knowledge_base.doc_cleaner import extract_pages
from archoptimize.knowledge_base.doc_downloader import download_source
from archoptimize.knowledge_base.knowledge_sources import load_sources
from archoptimize.retrieval.text_embedder import Embedder, FastEmbedEmbedder
from archoptimize.retrieval.vector_store import DEFAULT_INDEX_DIR, KnowledgeIndex
from archoptimize.schemas.doc_chunk import DocChunk

SOURCE_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "source_docs"


def build_chunks(cache_dir: Path = SOURCE_CACHE_DIR, redownload: bool = False) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    for source in load_sources():
        pdf = download_source(source, cache_dir, force=redownload)
        pages = extract_pages(pdf)
        doc_chunks = chunk_pages(source, pages)
        print(f"  {source.id_prefix:<5} {len(pages):>4} pages -> {len(doc_chunks):>5} chunks")
        chunks.extend(doc_chunks)
    return chunks


def build_index(
    chunks: list[DocChunk], index: KnowledgeIndex, embedder: Embedder, batch: int = 256
) -> None:
    index.reset()
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        index.add(part, embedder.embed_passages([c.text for c in part]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="index_builder")
    parser.add_argument("--redownload", action="store_true")
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    print("Extracting and chunking documents:")
    chunks = build_chunks(redownload=args.redownload)
    print(f"Embedding {len(chunks)} chunks (first run downloads the model, ~70 MB)...")
    index = KnowledgeIndex(args.index_dir)
    build_index(chunks, index, FastEmbedEmbedder())
    print(
        f"Done: {index.count()} chunks in {args.index_dir} ({time.perf_counter() - started:.0f}s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
