#!/usr/bin/env bash
# Apply the Hermes settings this repo manages to the running container.
#
# Runs on the server (deploy/deploy.sh calls it after `compose up`); also
# usable against a local test container. Every key is written with
# `hermes config set`, which validates the key and leaves config.yaml
# byte-identical when the value is unchanged. The gateway is restarted only
# when config.yaml actually changed.
#
# Keep SETTINGS in sync with docs/homeserver-hermes-architecture.md (모델 배분,
# MCP 서버와 도구, 보안).
#
# Before writing settings it installs each MCP server's locked dependencies
# into /opt/data/<server>/.venv, so the first MCP start does not download.
set -euo pipefail

container="${HERMES_CONTAINER:-hermes}"

# The image's init remaps the hermes user to HERMES_UID and fixes /opt/data
# ownership after the container starts. A `docker exec -u hermes` right after
# `compose up` can still run as the image default UID 10000 and fail to write
# /opt/data, so wait until hermes owns /opt/data and can write to it.
wait_for_container() {
  local i
  for ((i = 0; i < 60; i++)); do
    if docker exec -u hermes "$container" sh -c \
      'test "$(id -u)" = "$(stat -c %u /opt/data)" && test -w /opt/data' 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "configure: container $container not ready after 60s (hermes user cannot write /opt/data)" >&2
  exit 1
}

wait_for_container

# MCP servers under /opt/mcp (bind-mounted from mcp/). Each is a uv project.
MCP_SERVERS=(planner)

for name in "${MCP_SERVERS[@]}"; do
  docker exec -u hermes -w "/opt/mcp/$name" \
    -e UV_PROJECT_ENVIRONMENT="/opt/data/$name/.venv" \
    -e UV_CACHE_DIR=/opt/data/.cache/uv \
    -e UV_PYTHON_DOWNLOADS=never \
    "$container" uv sync --frozen --no-dev --quiet || {
      echo "configure: uv sync failed for MCP server $name" >&2
      exit 1
    }
done

# One "key<TAB>value" per line. Values are YAML literals.
SETTINGS=$(cat <<'EOF'
model.provider	openai-codex
model.default	gpt-6.2-sol
auxiliary.compression.provider	openai-codex
auxiliary.compression.model	gpt-6-luna
auth.adopt_external_logins	false
providers.exaone	{api: "https://api.exaone.ai/v1", key_env: EXAONE_API_KEY, transport: chat_completions, default_model: k-exaone_v2.5, extra_body: {temperature: 1.0, top_p: 0.95}}
fallback_providers	[{provider: exaone, model: k-exaone_v2.5}]
mcp_servers.planner	{command: uv, args: [run, --frozen, --no-dev, python, -m, planner.server], cwd: /opt/mcp/planner, connect_timeout: 120, timeout: 60, env: {NOTION_TOKEN: "${NOTION_TOKEN}", PLANNER_CONFIG: /opt/data/planner/planner.yaml, GOOGLE_TOKEN_FILE: /opt/data/planner/google_token.json, UV_PROJECT_ENVIRONMENT: /opt/data/planner/.venv, UV_CACHE_DIR: /opt/data/.cache/uv, UV_PYTHON_DOWNLOADS: never}}
platform_toolsets.discord	[memory, session_search, planner]
EOF
)

config_hash() {
  docker exec "$container" sha256sum /opt/data/config.yaml | cut -d' ' -f1
}

before=$(config_hash)

while IFS=$'\t' read -r key value; do
  [[ -z "$key" ]] && continue
  out=$(docker exec "$container" hermes config set "$key" "$value" 2>&1) || {
    echo "$out" >&2
    echo "configure: failed to set $key" >&2
    exit 1
  }
  # `config set` saves unknown keys with only a warning; treat that as an error.
  if grep -q "not a recognized config key" <<<"$out"; then
    echo "$out" >&2
    echo "configure: unknown key $key (fix SETTINGS)" >&2
    exit 1
  fi
done <<<"$SETTINGS"

after=$(config_hash)

if [[ "$before" == "$after" ]]; then
  echo "configure: no changes"
else
  echo "configure: config.yaml changed, restarting gateway"
  docker exec "$container" hermes gateway restart
fi
