"""What every input path (YAML, text, image) produces: the design plus its requirements."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.component_graph import ComponentGraph
from archoptimize.schemas.requirements import Requirements


class DesignSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design: ComponentGraph
    requirements: Requirements = Field(default_factory=Requirements)
