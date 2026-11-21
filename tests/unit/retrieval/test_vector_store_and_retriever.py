"""Real Chroma (in a temp folder) with a tiny fake embedder: no model download, no network."""

from __future__ import annotations

import pytest

from archoptimize.retrieval.pillar_retriever import PillarRetriever
from archoptimize.retrieval.review_evidence import (
    collect_review_evidence,
    design_facts,
    format_evidence,
    review_pillars,
)
from archoptimize.retrieval.vector_store import KnowledgeIndex
from archoptimize.schemas import Pillar
from archoptimize.schemas.doc_chunk import DocChunk
from evaluation.eval_cases import load_cases

VOCAB = ["availability", "zone", "encrypt", "public", "cost", "cache", "cardholder"]


class KeywordEmbedder:
    """Fake embedder: one dimension per vocabulary word (enough to test the plumbing)."""

    def _vec(self, text: str) -> list[float]:
        text = text.lower()
        return [float(text.count(w)) + 0.01 for w in VOCAB]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def chunk(cid: str, pillar: Pillar, text: str) -> DocChunk:
    return DocChunk(
        chunk_id=cid, pillar=pillar, doc_title="Doc", page=1, url="https://x#page=1", text=text
    )


CHUNKS = [
    chunk("rel-0000", Pillar.RELIABILITY, "Use multiple availability zone deployments. " * 3),
    chunk("rel-0001", Pillar.RELIABILITY, "Back up data and test restores regularly."),
    chunk("sec-0000", Pillar.SECURITY, "Encrypt data and block public access. encrypt encrypt"),
    chunk("cost-0000", Pillar.COST_OPTIMIZATION, "Right size to reduce cost. cost cost"),
    chunk("perf-0000", Pillar.PERFORMANCE_EFFICIENCY, "Add a cache for read heavy load. cache"),
    chunk("pci-0000", Pillar.COMPLIANCE, "Protect stored cardholder data. cardholder"),
]


@pytest.fixture
def retriever(tmp_path) -> PillarRetriever:
    index = KnowledgeIndex(tmp_path / "index")
    embedder = KeywordEmbedder()
    index.add(CHUNKS, embedder.embed_passages([c.text for c in CHUNKS]))
    return PillarRetriever(index, embedder)


def test_search_respects_pillar_filter_and_ranks_by_similarity(retriever):
    hits = retriever.retrieve("availability zone failure", Pillar.RELIABILITY, k=2)
    assert [h.chunk.chunk_id for h in hits] == ["rel-0000", "rel-0001"]
    assert hits[0].score > hits[1].score
    assert all(h.chunk.pillar is Pillar.RELIABILITY for h in hits)


def test_metadata_round_trips(retriever):
    hit = retriever.retrieve("cardholder", Pillar.COMPLIANCE, k=1)[0]
    assert hit.chunk == CHUNKS[-1]


def test_reset_empties_the_index(tmp_path):
    index = KnowledgeIndex(tmp_path / "i")
    index.add(CHUNKS[:1], [[1.0] * len(VOCAB)])
    assert index.count() == 1
    index.reset()
    assert index.count() == 0


def test_evidence_covers_each_pillar_and_pci_only_when_required(retriever):
    pci_case = load_cases(only="02_pci")[0].submission
    plain_case = load_cases(only="01_single")[0].submission
    assert Pillar.COMPLIANCE in review_pillars(pci_case)
    assert Pillar.COMPLIANCE not in review_pillars(plain_case)

    evidence = collect_review_evidence(pci_case, retriever, per_pillar=1)
    assert {c.pillar for c in evidence} == {
        Pillar.SECURITY,
        Pillar.RELIABILITY,
        Pillar.COST_OPTIMIZATION,
        Pillar.PERFORMANCE_EFFICIENCY,
        Pillar.COMPLIANCE,
    }
    assert len({c.chunk_id for c in evidence}) == len(evidence)  # no duplicates


def test_design_facts_mention_risky_settings():
    facts = design_facts(load_cases(only="02_pci")[0].submission)
    assert "publicly accessible data store" in facts and "unencrypted data" in facts


def test_evidence_block_shows_ids_for_citing():
    block = format_evidence(CHUNKS[:1])
    assert block.startswith("<documentation>") and 'id="rel-0000"' in block
