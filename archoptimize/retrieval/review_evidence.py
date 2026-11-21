"""Turn a design into per-pillar search queries and collect the evidence for a review.

Each query = what the pillar cares about + facts from this design (services, component
types, notable settings), so retrieval returns guidance relevant to THIS system.
"""

from __future__ import annotations

from archoptimize.retrieval.pillar_retriever import PillarRetriever
from archoptimize.schemas import DesignSubmission, Pillar
from archoptimize.schemas.component_graph import ComponentType
from archoptimize.schemas.doc_chunk import DocChunk
from archoptimize.schemas.requirements import ComplianceStandard

PILLAR_FOCUS: dict[Pillar, str] = {
    Pillar.SECURITY: "protect data encryption at rest and in transit, restrict public access, "
    "web application firewall, network security",
    Pillar.RELIABILITY: "high availability across multiple Availability Zones, eliminate single "
    "points of failure, failover, backups, recovery point and recovery time objectives",
    Pillar.COST_OPTIMIZATION: "right sizing, avoid over-provisioning, match capacity to demand, "
    "cost-effective resources within budget",
    Pillar.PERFORMANCE_EFFICIENCY: "scaling to demand, automatic scaling, caching, reduce "
    "latency, throughput of databases",
    Pillar.COMPLIANCE: "PCI DSS cardholder data protection, encryption, restrict access, "
    "network segmentation",
}


def design_facts(submission: DesignSubmission) -> str:
    design = submission.design
    services = sorted({c.aws_service for c in design.components if c.aws_service})
    facts = [", ".join(services)]
    if any(
        c.availability_zones == 1 and c.type is not ComponentType.CLIENT for c in design.components
    ):
        facts.append("single Availability Zone")
    if any(c.public and c.is_data_store for c in design.components):
        facts.append("publicly accessible data store")
    if any(
        c.encryption_at_rest is False or c.encryption_in_transit is False for c in design.components
    ):
        facts.append("unencrypted data")
    if any(c.backups_enabled is False for c in design.components):
        facts.append("no backups")
    return "; ".join(f for f in facts if f)


def review_pillars(submission: DesignSubmission) -> list[Pillar]:
    pillars = [
        Pillar.SECURITY,
        Pillar.RELIABILITY,
        Pillar.COST_OPTIMIZATION,
        Pillar.PERFORMANCE_EFFICIENCY,
    ]
    if submission.requirements.requires(ComplianceStandard.PCI_DSS):
        pillars.append(Pillar.COMPLIANCE)
    return pillars


def collect_review_evidence(
    submission: DesignSubmission, retriever: PillarRetriever, per_pillar: int = 2
) -> list[DocChunk]:
    """Top `per_pillar` chunks for each relevant pillar, without duplicates."""
    facts = design_facts(submission)
    seen: dict[str, DocChunk] = {}
    for pillar in review_pillars(submission):
        query = f"{PILLAR_FOCUS[pillar]}. {facts}"
        for hit in retriever.retrieve(query, pillar, k=per_pillar):
            seen.setdefault(hit.chunk.chunk_id, hit.chunk)
    return list(seen.values())


def format_evidence(chunks: list[DocChunk]) -> str:
    """Evidence block for prompts: each chunk with its id so the model can cite it."""
    blocks = [
        f'<chunk id="{c.chunk_id}" pillar="{c.pillar.value}" source="{c.doc_title}, p.{c.page}">\n'
        f"{c.text}\n</chunk>"
        for c in chunks
    ]
    return "<documentation>\n" + "\n".join(blocks) + "\n</documentation>"
