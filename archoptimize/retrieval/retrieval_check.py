"""Sanity-check retrieval quality with hand-written queries (Step 4 "Done when").

    uv run python -m archoptimize.retrieval.retrieval_check

Each query lists words that a relevant passage should contain. A query passes when at least
one of its top-k results (from the right pillar) contains one of those words.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from archoptimize.retrieval.pillar_retriever import PillarRetriever, default_retriever
from archoptimize.schemas.finding import Pillar


@dataclass(frozen=True)
class RetrievalProbe:
    query: str
    pillar: Pillar
    expected_any: tuple[str, ...]


PROBES = [
    RetrievalProbe(
        "database runs in a single Availability Zone, how to survive an AZ failure",
        Pillar.RELIABILITY,
        ("multi-az", "multiple availability zones", "availability zones"),
    ),
    RetrievalProbe(
        "S3 bucket is publicly readable and contains sensitive data",
        Pillar.SECURITY,
        ("public access", "block public", "s3"),
    ),
    # Queries are phrased the way reviewers build them (AWS vocabulary). Casual phrasing
    # ("instances are much larger than needed") ranked the first right-sizing chunk only
    # 8th — candidate for query rewriting / reranking in Step 10.
    RetrievalProbe(
        "over-provisioned instances much larger than the workload needs, right sizing",
        Pillar.COST_OPTIMIZATION,
        ("right siz", "rightsiz", "over-provision", "overprovision"),
    ),
    RetrievalProbe(
        "read-heavy database overloaded at high request rates, reduce latency",
        Pillar.PERFORMANCE_EFFICIENCY,
        ("cach", "read replica"),
    ),
    RetrievalProbe(
        "storing cardholder data and primary account numbers",
        Pillar.COMPLIANCE,
        ("cardholder", "pan", "account number"),
    ),
]


def run_probes(retriever: PillarRetriever, k: int = 4) -> list[tuple[RetrievalProbe, bool, list]]:
    results = []
    for probe in PROBES:
        hits = retriever.retrieve(probe.query, probe.pillar, k=k)
        ok = any(
            h.chunk.pillar is probe.pillar
            and any(word in h.chunk.text.lower() for word in probe.expected_any)
            for h in hits
        )
        results.append((probe, ok, hits))
    return results


def main() -> int:
    results = run_probes(default_retriever())
    for probe, ok, hits in results:
        print(f"{'PASS' if ok else 'FAIL'}  [{probe.pillar.value}] {probe.query}")
        for h in hits:
            preview = " ".join(h.chunk.text.split())[:110]
            print(f"      {h.score:.3f} {h.chunk.chunk_id:<10} p.{h.chunk.page:<4} {preview}…")
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed}/{len(results)} probes passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
