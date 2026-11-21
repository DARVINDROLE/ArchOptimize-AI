"""Compare two designs: which components and connections were added, removed or changed.

Pure code (no LLM), so the before/after picture always matches the actual change.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from archoptimize.schemas import ComponentGraph

_COMPARED_FIELDS = (
    "type",
    "aws_service",
    "instance_type",
    "replicas",
    "availability_zones",
    "autoscaling",
    "public",
    "encryption_at_rest",
    "encryption_in_transit",
    "backups_enabled",
    "data_classification",
)


class FieldChange(BaseModel):
    field: str
    before: str
    after: str


class DesignDiff(BaseModel):
    added_components: list[str] = Field(default_factory=list)
    removed_components: list[str] = Field(default_factory=list)
    changed_components: dict[str, list[FieldChange]] = Field(default_factory=dict)
    added_edges: list[str] = Field(default_factory=list)  # "a -> b"
    removed_edges: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_components
            or self.removed_components
            or self.changed_components
            or self.added_edges
            or self.removed_edges
        )

    def summary_lines(self) -> list[str]:
        lines = [f"+ added {c}" for c in self.added_components]
        lines += [f"- removed {c}" for c in self.removed_components]
        for cid, changes in self.changed_components.items():
            for ch in changes:
                lines.append(f"~ {cid}.{ch.field}: {ch.before} → {ch.after}")
        lines += [f"+ edge {e}" for e in self.added_edges]
        lines += [f"- edge {e}" for e in self.removed_edges]
        return lines


def _show(value: object) -> str:
    if value is None:
        return "unstated"
    if hasattr(value, "model_dump"):
        return ", ".join(f"{k}={v}" for k, v in value.model_dump().items())
    return str(getattr(value, "value", value))


def diff_designs(before: ComponentGraph, after: ComponentGraph) -> DesignDiff:
    old = {c.id: c for c in before.components}
    new = {c.id: c for c in after.components}
    changed: dict[str, list[FieldChange]] = {}
    for cid in old.keys() & new.keys():
        changes = [
            FieldChange(
                field=f, before=_show(getattr(old[cid], f)), after=_show(getattr(new[cid], f))
            )
            for f in _COMPARED_FIELDS
            if getattr(old[cid], f) != getattr(new[cid], f)
        ]
        if changes:
            changed[cid] = changes

    def edges(g: ComponentGraph) -> set[str]:
        return {f"{e.source} -> {e.target}" for e in g.edges}

    old_edges, new_edges = edges(before), edges(after)
    return DesignDiff(
        added_components=sorted(new.keys() - old.keys()),
        removed_components=sorted(old.keys() - new.keys()),
        changed_components=dict(sorted(changed.items())),
        added_edges=sorted(new_edges - old_edges),
        removed_edges=sorted(old_edges - new_edges),
    )
