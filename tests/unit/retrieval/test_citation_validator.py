from __future__ import annotations

from archoptimize.retrieval.citation_validator import validate_citations
from archoptimize.schemas import Finding, Pillar, Severity


def finding(id: str, citations: list[str]) -> Finding:
    return Finding(
        id=id,
        pillar=Pillar.RELIABILITY,
        severity=Severity.HIGH,
        title="t",
        evidence="e",
        recommendation="r",
        citation_chunk_ids=citations,
    )


def test_keeps_retrieved_ids_and_drops_invented_ones():
    check = validate_citations(
        [finding("A", ["rel-0001", "rel-9999", "rel-0001"]), finding("B", ["made-up"])],
        retrieved_ids={"rel-0001", "rel-0002"},
    )
    assert check.findings[0].citation_chunk_ids == ["rel-0001"]  # deduplicated, fake removed
    assert check.findings[1].citation_chunk_ids == []
    assert check.uncited_finding_ids == ["B"]
    assert check.removed_citations == 2


def test_no_retrieval_means_everything_is_uncited():
    check = validate_citations([finding("A", ["rel-0001"])], retrieved_ids=set())
    assert check.uncited_finding_ids == ["A"]
