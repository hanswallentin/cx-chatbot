#!/usr/bin/env bash
# Single command to run the full automated test suite (API, MCP server,
# backend/orchestrator + guardrails) against a disposable local venv — no
# Docker required. See README.md FAQ for details.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

PIP="$VENV_DIR/bin/pip"
PYTEST="$VENV_DIR/bin/pytest"

"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet \
  -r api/requirements.txt \
  -r mcp-server/requirements.txt \
  -r backend/requirements.txt

export CONFIG_PATH="$ROOT_DIR/config.yaml"

echo "== API tests =="
PYTHONPATH="$ROOT_DIR/api" "$PYTEST" api/tests -q

echo "== MCP server tests =="
PYTHONPATH="$ROOT_DIR/mcp-server" "$PYTEST" mcp-server/tests -q

echo "== Backend tests =="
PYTHONPATH="$ROOT_DIR/backend" "$PYTEST" backend/tests -q

echo
echo "All test suites passed."
