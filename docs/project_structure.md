# Project Structure — ArchOptimize AI

The target layout of the codebase, the naming rules, the rules that keep the layers clean, and where each piece of work goes.
It replaces `PLAN.md` §3. When code and this file disagree, update one of them in the same change.

---

## 1. Design principles

The layout follows a **layered ("clean") architecture**, the common industry pattern for maintainable services:

1. **The domain at the centre.** `schemas/` (`ComponentGraph`, `Finding`, `Review`…) knows nothing about LLMs, Chroma or Gradio.
2. **Dependencies point inward.** The UI uses the workflow, the workflow uses agents, and agents use infrastructure. Nothing imports "upward" (§4).
3. **Pure logic is separate from I/O.** Calculators, diagram rendering and YAML parsing are pure functions, so they're easy to test. Network, disk and LLM calls sit behind small interfaces.
4. **Interfaces are used where things vary.** `PriceSource`, `HistoryStore` and `get_llm(role)` let us swap a price file for the AWS Pricing API, or Groq for OpenRouter, without touching agents.
5. **Config and prompts are data, not code.** Model IDs live in YAML, and prompts in Markdown files.
6. **Names say what a thing does** (§2). A newcomer should guess a file's job from its path alone.
7. **One concept per module, one test file per module.** Tests mirror the package tree.
8. **Deployable from the repo root.** Hugging Face Spaces runs `app.py` from the root, so we keep a flat package folder rather than a `src/` layout.

---

## 2. Naming rules

| Rule | Example | Avoid |
|---|---|---|
| Package = product name, lowercase, no abbreviations | `archoptimize/` | `arb/` |
| Folder = the **capability** it provides (noun) | `calculators/`, `retrieval/`, `design_parsing/` | `tools/`, `rag/`, `normalize/` |
| Module = **what it is or does**, specific | `model_router.py`, `citation_validator.py`, `mermaid_diagram.py` | `router.py`, `utils.py`, `helpers.py`, `misc.py` |
| Agents end in their role | `security_reviewer.py`, `architect_agent.py` | `security.py`, `agent1.py` |
| Prompt file = same stem as its agent | `prompts/security_reviewer.md` | `prompt_v2.txt` |
| Tests = `test_<module>.py` in the mirrored folder | `tests/unit/llm/test_model_router.py` | `tests/test_stuff.py` |
| Data files say their content | `aws_prices_snapshot.json`, `knowledge_sources.yaml` | `data.json`, `config2.yaml` |
| No generic dumping grounds | put a helper next to the code that uses it | `common/`, `shared/`, `utils/` |

---

## 3. Directory tree (target)

`✅` = exists now · `◻` = planned, with the step that adds it in brackets

```
ArchOptimize-AI/
├─ app.py                                   ◻ [9]  HF Spaces entry point (thin): build the web app and launch it
│
├─ archoptimize/                            the Python package
│  ├─ __init__.py                           ✅      package version
│  │
│  ├─ core/                                 ✅      cross-cutting basics, no business logic
│  │  ├─ app_settings.py                    ✅      input size caps, timeouts, reviewer concurrency
│  │  ├─ errors.py                          ✅      ArchOptimizeError family → friendly UI messages
│  │  ├─ secret_redaction.py                ✅      redact API keys from any text
│  │  ├─ untrusted_input.py                 ◻      wrap user designs as data, never as instructions
│  │  └─ logging_setup.py                   ◻      logging with the redaction filter always on
│  │
│  ├─ config/                               data files only
│  │  ├─ llm_roles.yaml                     ✅      role → provider/model + requirements
│  │  └─ review_pillars.yaml                ◻ [5]  pillars, reviewer ↔ pillar, Critic rubric weights
│  │
│  ├─ schemas/                              ✅      DOMAIN CONTRACTS: pure Pydantic, no I/O
│  │  ├─ component_graph.py                 ✅      Component, Edge, ComponentGraph
│  │  ├─ requirements.py                    ✅      Requirements: SLO, RPS, latency, budget, compliance, region
│  │  ├─ design_submission.py               ✅      DesignSubmission = design + requirements (output of every parser)
│  │  ├─ finding.py                         ✅      Pillar, Severity, Citation, Finding
│  │  ├─ candidate_design.py                ◻ [6]  DesignChange, CandidateDesign, CriticScore
│  │  └─ review_result.py                   ◻ [5]  PillarScore, Verdict, ReviewResult
│  │
│  ├─ llm/                                  LLM ACCESS: the only place that talks to LLM APIs
│  │  ├─ role_config.py                     ✅      loads llm_roles.yaml
│  │  ├─ api_keys.py                        ✅      ProviderKeys: session-only, hidden values
│  │  ├─ model_catalog.py                   ✅      live OpenRouter/Groq model lists + 1 h cache
│  │  ├─ model_selector.py                  ✅      filter + rank free models for a role
│  │  ├─ model_cooldown.py                  ✅      skip recently failed models
│  │  ├─ groq_client.py                     ✅      Groq chat model factory
│  │  ├─ openrouter_client.py               ✅      OpenRouter chat model factory
│  │  ├─ model_router.py                    ✅      get_llm(role): try-next routing + fallback
│  │  └─ smoke_check.py                     ✅      live check: python -m archoptimize.llm.smoke_check
│  │
│  ├─ design_parsing/                       USER INPUT → ComponentGraph + Requirements
│  │  ├─ design_template.yaml               ✅      the YAML template users fill in
│  │  ├─ yaml_design_parser.py              ✅      no LLM
│  │  ├─ text_design_parser.py              ◻ [8]  LLM + structured output; unknowns → assumptions
│  │  └─ image_design_parser.py             ◻ post-MVP  vision model
│  │
│  ├─ calculators/                          ◻ [5]  PURE MATH: every number comes from here
│  │  ├─ price_source.py                    ◻      PriceSource interface + JsonPriceSource
│  │  ├─ monthly_cost.py                    ◻      monthly_cost(items)
│  │  ├─ capacity.py                        ◻      instances needed for RPS + headroom
│  │  ├─ availability.py                    ◻      series / parallel availability
│  │  └─ aws_prices_snapshot.json           ◻      price snapshot (date + source inside)
│  │
│  ├─ mcp_server/                           ◻ [7]  MCP WRAPPER: exposes calculators as MCP tools
│  │  ├─ calculator_server.py               ◻      FastMCP server (stdio)
│  │  └─ calculator_client.py               ◻      loads the MCP tools for agents
│  │
│  ├─ knowledge_base/                       ◻ [4]  OFFLINE: build the AWS docs index (run once)
│  │  ├─ knowledge_sources.yaml             ◻      doc URLs + pillar tags
│  │  ├─ doc_downloader.py                  ◻      download HTML/PDF
│  │  ├─ doc_cleaner.py                     ◻      HTML/PDF → clean text
│  │  ├─ doc_chunker.py                     ◻      ~500-token chunks + metadata
│  │  └─ index_builder.py                   ◻      embed → Chroma: python -m archoptimize.knowledge_base.index_builder
│  │
│  ├─ retrieval/                            ◻ [4]  ONLINE: search the index + verify citations
│  │  ├─ vector_store.py                    ◻      open the Chroma index (read-only)
│  │  ├─ pillar_retriever.py                ◻      pillar-filtered top-k search
│  │  └─ citation_validator.py              ◻      drop/flag findings citing chunks that weren't retrieved
│  │
│  ├─ agents/                               THE REVIEW BOARD: module + prompt + test per agent
│  │  ├─ agent_base.py                      ◻ [3]  load prompt → get_llm(role) → structured output
│  │  ├─ input_guard.py                     ◻ [5]  size caps + chunked prompt-injection check
│  │  ├─ reviewer_selector.py               ◻ [5]  decides which reviewers run
│  │  ├─ baseline_reviewer.py               ◻ [3]  single-LLM review (kept as the eval baseline)
│  │  ├─ reviewers/                         ◻ [5]
│  │  │  ├─ reviewer_base.py                ◻      retrieve → calculate → findings → validate citations
│  │  │  ├─ security_reviewer.py
│  │  │  ├─ reliability_reviewer.py
│  │  │  ├─ cost_reviewer.py
│  │  │  ├─ scalability_reviewer.py
│  │  │  └─ pci_compliance_reviewer.py
│  │  ├─ architect_agent.py                 ◻ [6]  3 candidate designs in one call
│  │  ├─ critic_agent.py                    ◻ [6]  rubric + calculator checks → winner
│  │  ├─ chair_agent.py                     ◻ [5]  verdict, pillar scores, trade-offs
│  │  └─ prompts/                           ◻      <agent_name>.md for each agent
│  │
│  ├─ review_workflow/                      ◻ [5]  LANGGRAPH ORCHESTRATION
│  │  ├─ workflow_state.py                  ◻      ReviewState
│  │  ├─ workflow_nodes.py                  ◻      thin adapters: state → agent → state update
│  │  ├─ workflow_graph.py                  ◻      wires nodes: parallel reviewers, Critic loop ≤ 2
│  │  └─ workflow_runner.py                 ◻      runs a review + streams progress events
│  │
│  ├─ reporting/                            OUTPUT FOR HUMANS (pure)
│  │  ├─ mermaid_diagram.py                 ✅      ComponentGraph → Mermaid
│  │  ├─ design_diff.py                     ◻ [6]  before/after diff + change list
│  │  └─ markdown_report.py                 ◻ [9]  ReviewResult → downloadable Markdown
│  │
│  ├─ review_history/                       ◻ [9]  SESSION HISTORY
│  │  └─ history_store.py                   ◻      HistoryStore interface + SessionHistoryStore
│  │
│  ├─ cli.py                                ✅      local CLI: `python -m archoptimize.cli preview <file.yaml>` / `template`
│  └─ web_ui/                               ◻ [9]  GRADIO
│     ├─ app_builder.py                     ◻      build_app(): assembles the interface
│     ├─ page_layout.py                     ◻      tabs and components
│     ├─ event_handlers.py                  ◻      button callbacks → review_workflow
│     └─ demo_mode.py                       ◻      serves precomputed reviews (no key needed)
│
├─ data/
│  ├─ knowledge_index/                      ◻ [4]  prebuilt Chroma index (shipped; Git LFS if > 10 MB)
│  └─ demo_reviews/                         ◻ [9]  precomputed review JSONs for demo mode
│
├─ evaluation/                              ◻ [2]  QUALITY MEASUREMENT (not shipped to users)
│  ├─ test_designs/*.yaml                   ◻      designs with planted flaws
│  ├─ expected_findings/*.json              ◻      expected flaws (pillar + component id) + verdict
│  ├─ scoring.py                            ◻      recall, false findings, verdict accuracy
│  ├─ run_evaluation.py                     ◻      python -m evaluation.run_evaluation
│  └─ results/                              ◻      dated JSON results (gitignored)
│
├─ tests/                                   mirrors archoptimize/
│  ├─ conftest.py                           ✅      shared fixtures (fake clock, model catalog)
│  ├─ fixtures/                             ✅      openrouter_models.json (+ sample designs later)
│  ├─ unit/                                 fast: no keys, no network (runs on every push)
│  │  ├─ core/                              ✅      test_secret_redaction.py
│  │  └─ llm/                               ✅      test_model_catalog.py, test_model_selector.py, test_model_router.py …
│  └─ live/                                 ✅      real API calls; only with `pytest -m live`
│
├─ docs/
│  ├─ project_brief.md                      ✅      problem, goals, requirements
│  ├─ project_overview.md                   ✅      flow, parts, scenarios, MVP
│  └─ project_structure.md                  ✅      this file
│
├─ .github/workflows/
│  ├─ ci.yml                                ◻ [M1] lint + unit tests on every push/PR
│  └─ deploy_to_hf_space.yml                ◻ [M1] on main: push to the HF Space (secret HF_TOKEN)
│
├─ README.md                                ✅      + HF Space metadata header (sdk: gradio, app_file: app.py)
├─ PLAN.md · AGENTS.md · CLAUDE.md          ✅      stay at the root (AI tools look for them there)
├─ pyproject.toml · uv.lock                 ✅      dependency source of truth
├─ requirements.txt                         ◻ [M1] generated by `uv export` for HF Spaces; never hand-edited
├─ .env.example · .gitignore · .gitattributes ✅
└─ LICENSE                                  ◻      MIT
```

---

## 4. Dependency rules (who may import whom)

```
  web_ui ──► review_workflow ──► agents ──► llm · retrieval · mcp_server → calculators · design_parsing
     │              │               │
     └──────────────┴───────────────┴──► reporting · review_history
                                                     ▼
                                (everything) ──► schemas ──► core
```

| Layer | May import | Must NOT import |
|---|---|---|
| `core`, `schemas` | stdlib, pydantic (schemas may use core) | anything else in the package |
| `calculators`, `reporting`, `design_parsing/yaml_design_parser` | schemas, core | llm, agents, web_ui |
| `llm`, `retrieval`, `knowledge_base`, `review_history`, `mcp_server` | schemas, core (mcp_server → calculators) | agents, review_workflow, web_ui |
| `agents` | all layers above, `prompts/` | review_workflow, web_ui |
| `review_workflow` | agents, schemas, core | web_ui |
| `web_ui`, `app.py` | review_workflow, reporting, review_history, schemas | llm directly |
| `evaluation` | review_workflow, agents, schemas | web_ui |

How the `AGENTS.md` hard rules map onto this structure:
- LLMs only via `llm.model_router.get_llm(role)`. No other module imports `langchain_groq` or `langchain_openai`.
- Numbers only from `calculators/` (called through MCP from Step 7).
- Prompts only in `agents/prompts/`; model IDs only in `config/llm_roles.yaml`.

These rules can later be enforced automatically by `import-linter` in CI.

---

## 5. Conventions

| Topic | Convention |
|---|---|
| Types | type hints everywhere; Pydantic v2 for all data crossing a boundary |
| Errors | raise `core.errors` subclasses; the UI maps them to friendly text; never show raw tracebacks |
| Logging | `logging.getLogger(__name__)`; redaction filter always on; never log keys or full user designs |
| Config precedence | code defaults → YAML in `config/` → environment variables → UI session values |
| Secrets | `.env` (local), UI session (deployed), GitHub/HF secrets (CI); nowhere else |
| Prompts | Markdown with `{placeholders}`; user input always passed through `untrusted_input` |
| Tests | external calls mocked in `unit/`; real calls only in `live/` with `@pytest.mark.live` |
| Commands | `uv run python -m pytest` · `uv run ruff check .` · `uv run python -m evaluation.run_evaluation` · `uv run python -m archoptimize.llm.smoke_check` |
| Commits | one step (or sub-step) per commit: `Step N: …`; CI green before deploy |
| Dependencies | `uv add <pkg>` only when a step needs it; regenerate `requirements.txt` with `uv export` |

---

## 6. Request flow mapped onto the folders

```
app.py → web_ui/event_handlers
   ├─ "Parse"  ─► design_parsing/* ─► schemas.ComponentGraph ─► reporting/mermaid_diagram  (confirm screen)
   └─ "Review" ─► review_workflow/workflow_runner ─► workflow_graph (LangGraph)
                    input_guard → reviewer_selector → reviewers/* ─┬─ retrieval/pillar_retriever + citation_validator
                                                                   ├─ mcp_server/calculator_client → calculators/*
                                                                   └─ llm/model_router.get_llm(role)
                    → architect_agent → critic_agent (loop ≤ 2) → chair_agent
                 ◄─ schemas.ReviewResult ─► reporting/design_diff + markdown_report ─► web_ui tabs + download
```

---

## 7. Migration from the first layout (done 2026-11-22)

| Current | New | Why |
|---|---|---|
| `arb/` | `archoptimize/` | package named after the product |
| `arb/providers/` | `archoptimize/llm/` | says what it provides |
| `providers/config.py` | `llm/role_config.py` | it loads role config, not general config |
| `providers/keys.py` | `llm/api_keys.py` (+ `redact` → `core/secret_redaction.py`) | specific name; redaction is shared |
| `providers/selector.py` | `llm/model_selector.py` | specific |
| `providers/cooldown.py` | `llm/model_cooldown.py` | specific |
| `providers/router.py` | `llm/model_router.py` | avoids a clash with the reviewer-selector agent |
| `providers/smoke.py` | `llm/smoke_check.py` | says what it does |
| `config/models.yaml` | `config/llm_roles.yaml` | it maps roles to models |
| `tests/test_providers.py` | `tests/unit/llm/test_*.py` (split per module) | mirrors the package |
| `PROJECT_*.md` (root) | `docs/project_*.md` | tidy root |
| plan names `graph/`, `rag/`, `ingest/`, `normalize/`, `render/`, `storage/`, `eval/` | `review_workflow/`, `retrieval/`, `knowledge_base/`, `design_parsing/`, `reporting/`, `review_history/`, `evaluation/` | descriptive names (§2) |
