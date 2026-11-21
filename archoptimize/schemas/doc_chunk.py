"""A short excerpt of AWS documentation, as stored in and returned by the knowledge index."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.finding import Pillar


class DocChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(description="Stable id, e.g. 'rel-0042'. Findings cite this.")
    pillar: Pillar
    doc_title: str
    page: int = Field(ge=1)
    url: str = Field(description="Link to the source page (PDF #page=N).")
    text: str


class RetrievedChunk(BaseModel):
    """A chunk returned by a search, with its similarity (1.0 = identical)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: DocChunk
    score: float
