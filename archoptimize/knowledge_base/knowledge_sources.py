"""Load knowledge_sources.yaml (the list of documents to index)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.finding import Pillar

SOURCES_FILE = Path(__file__).resolve().parent / "knowledge_sources.yaml"


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_prefix: str = Field(pattern=r"^[a-z]{2,6}$")
    pillar: Pillar
    title: str
    url: str

    @property
    def file_name(self) -> str:
        return f"{self.id_prefix}.pdf"


def load_sources(path: Path = SOURCES_FILE) -> list[KnowledgeSource]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = [KnowledgeSource.model_validate(s) for s in data["sources"]]
    prefixes = [s.id_prefix for s in sources]
    if len(prefixes) != len(set(prefixes)):
        raise ValueError("duplicate id_prefix in knowledge_sources.yaml")
    return sources
