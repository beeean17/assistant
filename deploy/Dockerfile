# Hermes runtime image for the home server.
# Built on the server itself (linux/amd64); no registry involved.
ARG HERMES_VERSION=v0.23.2
ARG UV_VERSION=0.13.5

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM nousresearch/hermes-agent:${HERMES_VERSION}

# The official image keeps its own uv under a versioned path in
# /opt/hermes/tools that is not on PATH. MCP servers are started with
# `uv run`, so put a pinned uv on PATH independently of that layout.
COPY --from=uv /uv /uvx /usr/local/bin/

# MCP servers (mcp/planner, mcp/jobs) are added here once they exist.
# Keep the official ENTRYPOINT (/init via s6-overlay): it fixes /opt/data
# ownership, drops to the hermes user and reaps MCP child processes.
