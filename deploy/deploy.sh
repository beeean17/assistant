#!/usr/bin/env bash
# Deploy origin/main to the home server over SSH (Tailscale).
#
# Usage: deploy/deploy.sh [--logs]
#   ASSISTANT_HOST  SSH host of the server (default: homeserver, an ~/.ssh/config alias)
#   --logs          follow container logs after deploying (Ctrl+C to stop)
#
# The server pulls from GitHub, so only pushed commits on main are deployed.
set -euo pipefail

host="${ASSISTANT_HOST:-homeserver}"
follow_logs=false

case "${1:-}" in
  "") ;;
  --logs) follow_logs=true ;;
  -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
esac

# Warn when local main and origin/main differ: the server only sees origin/main.
if git rev-parse --git-dir >/dev/null 2>&1; then
  git fetch -q origin main
  if [[ "$(git rev-parse main)" != "$(git rev-parse origin/main)" ]]; then
    echo "warning: local main ($(git rev-parse --short main)) != origin/main ($(git rev-parse --short origin/main)); deploying origin/main" >&2
  fi
  echo "deploying origin/main $(git rev-parse --short origin/main) to $host"
else
  echo "deploying origin/main to $host"
fi

# Fails (and deploys nothing) if the server checkout has local changes that
# conflict with the pull, or if it is not on main.
ssh "$host" bash -s <<'REMOTE'
set -euo pipefail
cd ~/assistant
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != main ]]; then
  echo "server checkout is on '$branch', not main; aborting" >&2
  exit 1
fi
git pull -q --ff-only
echo "server at $(git log -1 --oneline)"
docker compose -f deploy/compose.yaml up -d --build
docker compose -f deploy/compose.yaml ps
REMOTE

if $follow_logs; then
  ssh -t "$host" 'cd ~/assistant && docker compose -f deploy/compose.yaml logs -f --tail 50'
fi
