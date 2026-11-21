"""Pick OpenRouter models for a role: free only -> filter by requirements -> rank."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from archoptimize.llm.model_catalog import ModelInfo
from archoptimize.llm.role_config import RoleRequirements


def meets_requirements(m: ModelInfo, req: RoleRequirements) -> bool:
    if not m.is_free:
        return False
    if "text" not in m.input_modalities or "text" not in m.output_modalities:
        return False
    if req.image_input and "image" not in m.input_modalities:
        return False
    # We require real JSON-schema support ("structured_outputs"), not just JSON mode,
    # because every agent output is parsed into a Pydantic model.
    if req.structured_output and "structured_outputs" not in m.supported_parameters:
        return False
    if req.tools and "tools" not in m.supported_parameters:
        return False
    return m.context_length >= req.min_context


def select_models(
    models: Iterable[ModelInfo],
    req: RoleRequirements,
    *,
    exclude_families: Iterable[str] = (),
    prefer: Sequence[str] = (),
    is_cooling: Callable[[str], bool] = lambda _id: False,
    limit: int = 3,
) -> list[ModelInfo]:
    """Return up to `limit` models, best first.

    Ranking: config `prefer` substrings first (in order), then larger context, then id
    (so the result is deterministic).
    """
    excluded = {f.lower() for f in exclude_families}
    prefer_lower = [p.lower() for p in prefer]

    def preference(m: ModelInfo) -> int:
        mid = m.id.lower()
        return next((i for i, p in enumerate(prefer_lower) if p in mid), len(prefer_lower))

    usable = [
        m
        for m in models
        if meets_requirements(m, req) and m.family not in excluded and not is_cooling(m.id)
    ]
    usable.sort(key=lambda m: (preference(m), -m.context_length, m.id))
    return usable[:limit]
