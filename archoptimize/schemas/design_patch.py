"""A redesign expressed as a patch: what to add, change or remove in the original design.

Why patches instead of whole designs? The Architect proposes three options in ONE call;
three complete designs would be large (slow, and over the Groq free-tier token budget).
A patch is small, keeps unchanged component ids stable (so the before/after diff is exact),
and is applied by code, which also validates the result.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.component_graph import (
    COMPONENT_ID_PATTERN,
    AutoscalingConfig,
    Component,
    ComponentGraph,
    DataClassification,
    Edge,
)


class ComponentUpdate(BaseModel):
    """Changes to an existing component. A field left out (null) stays as it is."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=COMPONENT_ID_PATTERN, description="Id of an EXISTING component.")
    aws_service: str | None = None
    instance_type: str | None = None
    replicas: int | None = Field(default=None, ge=1, le=1000)
    availability_zones: int | None = Field(default=None, ge=1, le=6)
    autoscaling: AutoscalingConfig | None = None
    public: bool | None = None
    encryption_at_rest: bool | None = None
    encryption_in_transit: bool | None = None
    backups_enabled: bool | None = None
    data_classification: DataClassification | None = None
    notes: str | None = Field(default=None, max_length=500)


class EdgeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str


class DesignPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    add_components: list[Component] = Field(
        default_factory=list, description="New components with NEW unique ids."
    )
    update_components: list[ComponentUpdate] = Field(default_factory=list)
    remove_component_ids: list[str] = Field(default_factory=list)
    add_edges: list[Edge] = Field(default_factory=list)
    remove_edges: list[EdgeRef] = Field(
        default_factory=list, description="Edges to delete (edges of removed components go too)."
    )


class PatchError(ValueError):
    pass


def apply_design_patch(graph: ComponentGraph, patch: DesignPatch) -> ComponentGraph:
    """Return a new, validated design. Raises PatchError if the patch does not fit."""
    components = {c.id: c for c in graph.components}
    for cid in patch.remove_component_ids:
        if cid not in components:
            raise PatchError(f"cannot remove unknown component '{cid}'")
        del components[cid]
    for update in patch.update_components:
        if update.id not in components:
            raise PatchError(f"cannot update unknown component '{update.id}'")
        changes = update.model_dump(exclude={"id"}, exclude_none=True)
        if update.autoscaling is not None:
            changes["autoscaling"] = update.autoscaling
        components[update.id] = components[update.id].model_copy(update=changes)
    for new in patch.add_components:
        if new.id in components:
            raise PatchError(f"component id '{new.id}' already exists")
        components[new.id] = new

    removed_edges = {(r.source, r.target) for r in patch.remove_edges}
    edges = [
        e
        for e in graph.edges
        if (e.source, e.target) not in removed_edges
        and e.source in components
        and e.target in components
    ]
    edges += patch.add_edges
    try:
        # re-validate everything (ids, references, autoscaling limits) via the schema
        return ComponentGraph.model_validate(
            {
                **graph.model_dump(exclude={"components", "edges"}),
                "components": [c.model_dump() for c in components.values()],
                "edges": [e.model_dump(by_alias=True) for e in edges],
            }
        )
    except ValueError as exc:
        raise PatchError(f"the patched design is invalid: {exc}") from exc
