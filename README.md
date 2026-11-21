# ArchOptimize AI — Architecture Review Board Agent

A multi-agent system that reviews an AWS system design against its requirements (SLO, RPS, budget, compliance), cites AWS Well-Architected guidance, and proposes a revised design.

Work in progress — see `PROJECT_BRIEF.md`, `PROJECT_OVERVIEW.md` and `PLAN.md`.

## Local setup

```powershell
uv sync                       # create .venv and install deps
Copy-Item .env.example .env   # then put your own keys in .env
uv run pytest                 # tests (no keys needed)
uv run python -m arb.providers.smoke   # live check: needs keys in .env
```
