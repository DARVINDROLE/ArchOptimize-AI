"""Call the calculator MCP server from the agents (via langchain-mcp-adapters).

`measure_designs_via_mcp()` starts the server as a subprocess (stdio), calls the
`measure_designs` tool once for a batch of designs, and records the call for the trace
shown in the UI. If MCP is unavailable, it falls back to calling the same calculators
in-process and says so in the trace — the numbers are identical either way.

Set ARCHOPTIMIZE_CALCULATORS=local to skip MCP (e.g. in unit tests).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

from archoptimize.calculators.design_metrics import measure_design
from archoptimize.core.secret_redaction import redact
from archoptimize.schemas import ComponentGraph, Requirements
from archoptimize.schemas.design_metrics import DesignMetrics, ToolCallRecord

log = logging.getLogger(__name__)

SERVER_NAME = "calculators"
MCP_TIMEOUT_SECONDS = 60


def _server_config() -> dict:
    return {
        SERVER_NAME: {
            "command": sys.executable,
            "args": ["-m", "archoptimize.mcp_server.calculator_server"],
            "transport": "stdio",
        }
    }


def _tool_payload(result: object) -> object:
    """langchain-mcp-adapters returns tool output as text/JSON content; turn it into data."""
    if isinstance(result, str):
        return json.loads(result)
    if isinstance(result, list):  # list of content blocks
        texts = [
            b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "") for b in result
        ]
        joined = "".join(texts)
        return json.loads(joined) if joined else result
    return result


async def _call_mcp(tool_name: str, args: dict) -> object:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(_server_config())
    tools = {t.name: t for t in await client.get_tools()}
    return _tool_payload(await tools[tool_name].ainvoke(args))


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # already inside an event loop (e.g. Gradio): run in a fresh thread's loop
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def measure_designs_via_mcp(
    designs: list[ComponentGraph], req: Requirements
) -> tuple[list[DesignMetrics], ToolCallRecord]:
    started = time.perf_counter()
    if os.getenv("ARCHOPTIMIZE_CALCULATORS", "mcp").lower() != "local":
        args = {
            "designs": [d.model_dump(mode="json", by_alias=True) for d in designs],
            "requirements": req.model_dump(mode="json"),
        }
        try:
            payload = _run(
                asyncio.wait_for(_call_mcp("measure_designs", args), MCP_TIMEOUT_SECONDS)
            )
            items = payload if isinstance(payload, list) else [payload]
            metrics = [DesignMetrics.model_validate(m) for m in items]
            if len(metrics) == len(designs):
                return metrics, ToolCallRecord(
                    tool="measure_designs",
                    via="mcp",
                    summary=f"{len(designs)} design(s)",
                    seconds=round(time.perf_counter() - started, 2),
                )
            raise ValueError("MCP returned a different number of results")
        except Exception as exc:
            log.warning(
                "MCP calculators unavailable, using local fallback: %s", redact(str(exc))[:200]
            )
    metrics = [measure_design(d, req) for d in designs]
    return metrics, ToolCallRecord(
        tool="measure_designs",
        via="local fallback",
        summary=f"{len(designs)} design(s)",
        seconds=round(time.perf_counter() - started, 2),
    )
