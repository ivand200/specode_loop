#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/specode_loop.py"
AUTH_MODE="${SPECODE_LOOP_AUTH_E2E_MODE:-oauth}"
PROJECT_DIR=""
STDOUT_FILE=""
STDERR_FILE=""

fail() {
  printf 'Real auth E2E failure: %s\n' "$*" >&2
  if [[ -n "$PROJECT_DIR" ]]; then
    printf 'Project: %s\n' "$PROJECT_DIR" >&2
    printf 'stdout: %s\n' "$STDOUT_FILE" >&2
    printf 'stderr: %s\n' "$STDERR_FILE" >&2
  fi
  exit 1
}

cleanup() {
  if [[ "${SPECODE_LOOP_AUTH_E2E_KEEP:-0}" != "1" && -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
    rm -rf "$PROJECT_DIR"
  fi
}

assert_contains() {
  local file="$1"
  local expected="$2"

  grep -Fq -- "$expected" "$file" || fail "expected $file to contain: $expected"
}

make_project() {
  PROJECT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode-loop-auth-e2e.XXXXXX")"
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd -P)"
  STDOUT_FILE="$PROJECT_DIR/auth-e2e.stdout"
  STDERR_FILE="$PROJECT_DIR/auth-e2e.stderr"

  cat >"$PROJECT_DIR/prd.md" <<'EOF'
# PRD: Authentication Request Fixture

Verify that Specode Loop can make a real Codex request through Docker Sandbox
using the explicitly selected authentication mode.
EOF

  cat >"$PROJECT_DIR/plan.md" <<'EOF'
# Plan: Authentication Request Fixture

## [x] Phase 1: Authentication request fixture

**Type**: AFK

The fixture is already complete. No project changes are required.
EOF
}

main() {
  local expected_auth
  local -a args

  trap cleanup EXIT

  case "$AUTH_MODE" in
    oauth)
      expected_auth="Authentication: OAuth"
      ;;
    api-key)
      expected_auth="Authentication: API key (explicit opt-in)"
      ;;
    *)
      fail "SPECODE_LOOP_AUTH_E2E_MODE must be oauth or api-key"
      ;;
  esac

  command -v sbx >/dev/null 2>&1 || fail "sbx is not installed or not on PATH"
  command -v uv >/dev/null 2>&1 || fail "uv is not installed or not on PATH"

  make_project
  args=("$PROJECT_DIR" --max-iterations 1 --auth "$AUTH_MODE")
  if [[ -n "${SPECODE_LOOP_AUTH_E2E_MODEL:-}" ]]; then
    args+=(--model "$SPECODE_LOOP_AUTH_E2E_MODEL")
  fi

  if ! (cd "$ROOT_DIR" && uv run python "$RUNNER" "${args[@]}") >"$STDOUT_FILE" 2>"$STDERR_FILE"; then
    sed -n '1,240p' "$STDOUT_FILE" >&2 || true
    sed -n '1,240p' "$STDERR_FILE" >&2 || true
    fail "runner did not complete the real Codex request"
  fi

  assert_contains "$STDOUT_FILE" "$expected_auth"
  assert_contains "$STDOUT_FILE" "Starting non-interactive Codex run in Docker Sandbox"
  assert_contains "$STDOUT_FILE" "ALL TASKS DONE sentinel detected"
  assert_contains "$PROJECT_DIR/specode_loop.log" "$expected_auth"
  assert_contains "$PROJECT_DIR/specode_loop.log" "ALL TASKS DONE sentinel detected"

  printf 'Real Codex authentication E2E passed (%s).\n' "$AUTH_MODE"
  if [[ "${SPECODE_LOOP_AUTH_E2E_KEEP:-0}" == "1" ]]; then
    printf 'Artifacts kept at: %s\n' "$PROJECT_DIR"
  fi
}

main "$@"
