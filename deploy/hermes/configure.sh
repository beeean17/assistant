#!/usr/bin/env bash
# Apply the Hermes settings this repo manages to the running container.
#
# Runs on the server (deploy/deploy.sh calls it after `compose up`); also
# usable against a local test container. Every key is written with
# `hermes config set`, which validates the key and leaves config.yaml
# byte-identical when the value is unchanged. The gateway is restarted only
# when config.yaml actually changed.
#
# Keep SETTINGS in sync with docs/homeserver-hermes-architecture.md (모델 배분).
set -euo pipefail

container="${HERMES_CONTAINER:-hermes}"

# One "key<TAB>value" per line. Values are YAML literals.
SETTINGS=$(cat <<'EOF'
model.provider	openai-codex
model.default	gpt-6.2-sol
auxiliary.compression.provider	openai-codex
auxiliary.compression.model	gpt-6-luna
auth.adopt_external_logins	false
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
