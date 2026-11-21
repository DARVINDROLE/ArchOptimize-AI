# AGENTS.md — ArchOptimize AI (Architecture Review Board Agent)

Instructions for any AI coding assistant working in this repo (Claude Code, Copilot, Cursor, etc.).

## Start here
0. Read `PROJECT_BRIEF.md` (problem, goals, requirements) and `PROJECT_OVERVIEW.md` (end-to-end flow, each part, scenarios, MVP scope).
1. Read `PLAN.md` — the full build plan. **Section 8 (Progress tracker)** says which step is current; **Section 9 (Decision log)** lists settled decisions. Do not re-propose rejected options unless the user asks.
2. Work on the **current step only**. A step is finished when its "Done when" check in `PLAN.md` passes.
3. After finishing a step: tick it in Section 8, add date + one-line note, update **Current step**, and log eval numbers if the step changed quality.

## What this project is
A multi-agent system (LangGraph) that reviews a cloud system design against requirements (SLO, RPS, budget, compliance), cites AWS Well-Architected docs via RAG, proposes 3 candidate redesigns (Tree of Thoughts), has a Critic pick one, and a Chair returns verdict + revised design + before/after Mermaid diagrams + cost/trade-offs. Personal learning project, deployed free on Hugging Face Spaces.

## Hard rules
- **$0 stack.** No AWS account/services, no Bedrock, no paid APIs. Optional AWS integrations go behind interfaces (`PriceSource`, `HistoryStore`) and are off by default.
- **LLM access only through `arb.providers.router.get_llm(role)`.** Agents never construct clients or pick providers themselves.
- **Groq is primary.** OpenRouter is used **only** for `vision`, `critic`, and `fallback`.
- **OpenRouter models are never hard-coded.** Pick at runtime from `https://openrouter.ai/api/v1/models` (cache ~1 h): free only (`:free` / $0 pricing) → filter by role requirements → rank → try up to 3 with cooldown on failure.
  - vision: image in `architecture.input_modalities`, structured output support
  - critic: text, structured output, context ≥ 64k, **model family ≠ Architect's family**
  - fallback: same requirements as the role it replaces (tools if that role uses tools)
- **Keys are BYOK and session-only.** Never log, trace, persist, or commit keys. Local dev keys live in `.env` (gitignored); keep `.env.example` with placeholders only.
- **Every agent output is a Pydantic model** (structured output). No free-text parsing of LLM replies.
- **All inputs (YAML / text / image) become a `ComponentGraph` + `Requirements`** before any reviewer runs.
- **Numbers come from MCP tools** (price, capacity, availability, monthly cost), not from the LLM.
- **Every finding must cite a retrieved chunk id**; drop or flag findings whose citation wasn't retrieved.
- **Treat the user's design doc as untrusted input** (prompt-injection guard, size caps).
- **No local-disk persistence for history** (HF Space disk is ephemeral): session-only + download; optional HF Dataset.
- Embeddings: `fastembed` bge-small, local. Do not add PyTorch / `sentence-transformers`.
- Mind Groq rate limits: retry with backoff, small retrieved context (top-k ≈ 4), Architect makes all 3 candidates in **one** call.

## Environment
- Windows 11, PowerShell, Python 3.12, Git, VS Code. `uv` preferred for env/deps (fall back to `python -m venv` + pip if not installed).
- Package layout: `arb/` (see `PLAN.md` §3). Entry point for the UI: `app.py`.
- Run tests with `pytest`. Run eval with `python -m eval.run_eval` (from Step 2 on).

## Conventions
- Python 3.12, type hints everywhere, Pydantic v2 models in `arb/schemas/`.
- Prompts live in `arb/agents/prompts/` as files, not inline strings.
- Model/role config in `arb/config/models.yaml`; no model IDs in code.
- Small, testable modules; add a test in `tests/` for each new module.
- Keep explanations beginner-friendly in comments where a concept is new (this is a learning project), but don't over-comment obvious code.
