"""Text → vector (embedding). Similar meaning → nearby vectors, which is what search uses.

We use BAAI/bge-small-en-v1.5 through `fastembed`: it runs locally on CPU with ONNX, so
there is no PyTorch and no API cost. bge models embed questions and passages slightly
differently, hence `embed_query` vs `embed_passages`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "fastembed"


class Embedder(Protocol):
    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL, cache_dir: Path = MODEL_CACHE_DIR):
        from fastembed import TextEmbedding  # heavy import, only when actually used

        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.passage_embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()
