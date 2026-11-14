#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Self-hosted runner for the ListenBrainz autoposter. Meant to be called
# from cron daily on the 16th–28th (see README); it posts at most once a
# month, so extra runs are harmless.
#
#   scripts/run.sh              # post for real
#   scripts/run.sh --dry-run    # preview only, writes ./preview.png
#   scripts/run.sh --force      # post even if this month was already posted
#
# Reads credentials from .env in the repo root and appends output to
# logs/YYYY-MM.log. Uses .venv/bin/python if present; set PYTHON to
# override.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Prefer the project's virtualenv; fall back to the system python3.
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python
  else PYTHON="$(command -v python3 || true)"; fi
fi
if [[ -z "$PYTHON" ]]; then
  echo "✗ python3 not found — install Python 3.10+ or set PYTHON" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "✗ $REPO_DIR/.env not found — copy .env.example and fill it in" >&2
  exit 1
fi

# Pass through --dry-run / --force to the poster.
EXTRA_ARGS=("$@")
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && export DRY_RUN=1
done

mkdir -p logs
LOG="logs/$(date -u +%Y-%m).log"

# Hold a lock so an overlapping manual + cron run can't double-post.
exec 9>"logs/.run.lock"
if command -v flock >/dev/null && ! flock -n 9; then
  echo "✗ another run is already in progress" >&2
  exit 1
fi

{
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') run start ($("$PYTHON" --version 2>&1)${DRY_RUN:+, dry run}) ==="
  set +e
  "$PYTHON" -m autoposter --env-file .env ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
  status=$?
  set -e
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') run end (exit $status) ==="
  echo
  exit "$status"
} 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
