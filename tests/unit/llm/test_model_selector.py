from __future__ import annotations

from archoptimize.llm.model_selector import select_models
from archoptimize.llm.role_config import RoleRequirements

LARGE_CONTEXT = RoleRequirements(min_context=64_000)


def ids(models):
    return [m.id for m in models]


def test_vision_role_only_gets_image_models(openrouter_models):
    chosen = select_models(openrouter_models, RoleRequirements(image_input=True))
    assert ids(chosen) == ["google/gemma-vision:free"]


def test_filters_out_unfit_models(openrouter_models):
    chosen = ids(select_models(openrouter_models, LARGE_CONTEXT))
    assert "mistral/small-json-mode:free" not in chosen  # JSON mode only, no schema support
    assert "meta-llama/tiny:free" not in chosen  # context too small
    assert "anthropic/paid-model" not in chosen  # not free
    assert "openrouter/auto" not in chosen  # meta-router


def test_ranks_by_context_by_default(openrouter_models):
    assert select_models(openrouter_models, LARGE_CONTEXT)[0].id == "qwen/qwen3-big:free"


def test_preferred_models_rank_first(openrouter_models):
    chosen = select_models(openrouter_models, LARGE_CONTEXT, prefer=["gemma"])
    assert chosen[0].id == "google/gemma-vision:free"


def test_excludes_families(openrouter_models):
    chosen = select_models(openrouter_models, LARGE_CONTEXT, exclude_families={"openai"})
    assert "openai/gpt-oss-120b:free" not in ids(chosen)


def test_skips_cooling_models_and_respects_limit(openrouter_models):
    cooling = select_models(
        openrouter_models, LARGE_CONTEXT, is_cooling=lambda model_id: model_id.startswith("qwen")
    )
    assert all(not m.id.startswith("qwen") for m in cooling)
    assert len(select_models(openrouter_models, LARGE_CONTEXT, limit=1)) == 1
