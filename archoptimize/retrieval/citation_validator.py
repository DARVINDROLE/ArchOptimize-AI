"""Check citations: a finding may only cite chunks that were actually retrieved for it.

LLMs sometimes invent plausible-looking ids ("rel-9999"). We remove any cited id that was
not in the retrieved set, and report which findings end up with no valid citation
(the UI shows them as "uncited"; the eval measures the citation rate).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from archoptimize.schemas.finding import Finding


@dataclass(frozen=True)
class CitationCheck:
    findings: list[Finding]  # citations cleaned
    uncited_finding_ids: list[str]  # findings left without any valid citation
    removed_citations: int  # invented / not-retrieved ids that were dropped


def validate_citations(findings: Iterable[Finding], retrieved_ids: set[str]) -> CitationCheck:
    cleaned: list[Finding] = []
    uncited: list[str] = []
    removed = 0
    for f in findings:
        valid = [cid for cid in dict.fromkeys(f.citation_chunk_ids) if cid in retrieved_ids]
        removed += len(set(f.citation_chunk_ids)) - len(valid)
        cleaned.append(f.model_copy(update={"citation_chunk_ids": valid}))
        if not valid:
            uncited.append(f.id)
    return CitationCheck(cleaned, uncited, removed)
