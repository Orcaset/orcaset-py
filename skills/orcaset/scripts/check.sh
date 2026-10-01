#!/usr/bin/env bash
# Run ruff and pyrefly over a model directory (default: current directory).
# Usage: check.sh [dir]
set -uo pipefail

dir="${1:-.}"
status=0

# Run a tool from PATH. If it is not installed, try uvx. If neither can start it, say so.
run_tool() {
  local name=$1
  shift
  if command -v "$name" >/dev/null 2>&1; then
    "$name" "$@"
    return $?
  fi
  if command -v uvx >/dev/null 2>&1; then
    uvx "$name" "$@"
    return $?
  fi
  echo "wasn't able to run ${name}" >&2
  return 1
}

echo "== ruff =="
run_tool ruff check --isolated --no-cache --target-version py314 --fix "$dir" || status=1

echo "== pyrefly =="
run_tool pyrefly check \
  --preset default \
  --python-version 3.14 \
  --error implicit-any \
  --error unused-ignore \
  --strict-callable-subtyping=true \
  --min-severity warn \
  --summary none \
  --progress-bar no \
  "$dir" || status=1

exit "$status"
