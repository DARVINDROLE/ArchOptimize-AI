"""MCP wrapper around archoptimize.calculators.

MCP (Model Context Protocol) is a standard way to expose tools to AI agents. The server runs
as a separate process and talks over stdio; any MCP client (our agents, Claude Desktop,
an IDE) can list and call the same calculators.

Run it standalone:  uv run python -m archoptimize.mcp_server.calculator_server
"""
