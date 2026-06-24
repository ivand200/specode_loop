#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/specode_loop.py"
EXAMPLE_PROJECT="$ROOT_DIR/examples/basic"
ENV_FILE="${SPECODE_LOOP_PYTHON_E2E_ENV:-${SPECODE_LOOP_E2E_ENV:-}}"
PROJECT_DIR=""
STDOUT_FILE=""
STDERR_FILE=""
FAILED=0

log() {
  printf '%s\n' "$*"
}

keep_artifacts() {
  [[ "${SPECODE_LOOP_PYTHON_E2E_KEEP:-0}" == "1" || "${SPECODE_LOOP_KEEP_E2E_ARTIFACTS:-0}" == "1" ]]
}

fail() {
  FAILED=1
  printf 'Python E2E failure: %s\n' "$*" >&2
  if [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
    printf 'Project left for inspection: %s\n' "$PROJECT_DIR" >&2
    [[ -n "$STDOUT_FILE" ]] && printf 'stdout transcript: %s\n' "$STDOUT_FILE" >&2
    [[ -n "$STDERR_FILE" ]] && printf 'stderr transcript: %s\n' "$STDERR_FILE" >&2
  fi
  exit 1
}

cleanup() {
  if [[ "$FAILED" != "1" ]] && ! keep_artifacts && [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
    rm -rf "$PROJECT_DIR"
  fi
}

load_env() {
  if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

assert_file_contains() {
  local file="$1"
  local needle="$2"

  grep -Fq -- "$needle" "$file" || fail "expected $file to contain: $needle"
}

assert_file_exact() {
  local file="$1"
  local expected="$2"
  local actual

  [[ -f "$file" ]] || fail "expected file to exist: $file"
  actual="$(cat "$file")"
  [[ "$actual" == "$expected" ]] || fail "expected $file to contain exactly: $expected"
}

assert_project_command_exact() {
  local expected="$1"
  local project_dir="$2"
  shift 2
  local actual

  actual="$(cd "$project_dir" && "$@")" || fail "expected project command to succeed: $*"
  [[ "$actual" == "$expected" ]] || fail "expected command output exactly: $expected"
}

assert_path_missing() {
  local path="$1"

  if [[ -e "$path" ]]; then
    fail "expected path to be absent: $path"
  fi
}

assert_executable() {
  local path="$1"

  [[ -x "$path" ]] || fail "expected file to be executable: $path"
}

assert_count() {
  local expected="$1"
  local actual="$2"
  local label="$3"

  [[ "$actual" == "$expected" ]] || fail "expected $label to be $expected, got $actual"
}

count_file_matches() {
  local pattern="$1"
  local file="$2"

  grep -Ec "$pattern" "$file" || true
}

make_project() {
  PROJECT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode_loop-python-e2e.XXXXXX")"
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd -P)"
  STDOUT_FILE="$PROJECT_DIR/specode_loop_python_e2e.stdout"
  STDERR_FILE="$PROJECT_DIR/specode_loop_python_e2e.stderr"

  cp -R "$EXAMPLE_PROJECT/." "$PROJECT_DIR"
}

main() {
  local -a args

  trap cleanup EXIT
  load_env

  command -v sbx >/dev/null 2>&1 || fail "sbx is not installed or not on PATH"
  command -v uv >/dev/null 2>&1 || fail "uv is not installed or not on PATH"

  make_project
  log "Python E2E project: $PROJECT_DIR"

  args=("$PROJECT_DIR" --max-iterations 5)
  if [[ -n "${SPECODE_LOOP_PYTHON_E2E_MODEL:-${SPECODE_LOOP_E2E_MODEL:-}}" ]]; then
    args+=(--model "${SPECODE_LOOP_PYTHON_E2E_MODEL:-${SPECODE_LOOP_E2E_MODEL:-}}")
  fi

  if ! (cd "$ROOT_DIR" && uv run python "$RUNNER" "${args[@]}") >"$STDOUT_FILE" 2>"$STDERR_FILE"; then
    cat "$STDOUT_FILE" >&2 || true
    cat "$STDERR_FILE" >&2 || true
    fail "Python runner exited before completing the e2e task"
  fi

  cat "$STDOUT_FILE"

  assert_file_contains "$PROJECT_DIR/prd.md" "## Problem Statement"
  assert_file_contains "$PROJECT_DIR/prd.md" "## User Stories"
  assert_file_contains "$PROJECT_DIR/prd.md" "## Implementation Decisions"
  assert_file_contains "$PROJECT_DIR/prd.md" "## Testing Decisions"
  assert_file_contains "$PROJECT_DIR/plan.md" "# Plan: Specode Loop Request Response Fixture"
  assert_file_contains "$PROJECT_DIR/plan.md" "> Source PRD: prd.md"
  assert_file_contains "$PROJECT_DIR/plan.md" "## Architectural decisions"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 1: Seed Request Artifact"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 2: Deterministic Response Artifact"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 3: Reviewable Transcript"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 4: Executable Integration Check"
  assert_file_contains "$PROJECT_DIR/plan.md" "### Acceptance criteria"
  assert_file_contains "$PROJECT_DIR/plan.md" "## Blocked by"
  assert_file_exact "$PROJECT_DIR/request.txt" $'REQUEST_ID: specode-basic-001\nUSER_REQUEST: Summarize the Specode Loop demo state.\nEXPECTED_RESPONSE_KIND: deterministic-summary'
  assert_file_exact "$PROJECT_DIR/response.txt" $'RESPONSE_ID: specode-basic-001\nSTATUS: complete\nSUMMARY: Specode Loop can turn one local request into one deterministic response.'
  assert_file_exact "$PROJECT_DIR/transcript.md" $'# Specode Loop Request/Response Transcript\n\n## Request\n\nSummarize the Specode Loop demo state.\n\n## Response\n\nSpecode Loop can turn one local request into one deterministic response.'
  assert_executable "$PROJECT_DIR/verify.sh"
  assert_project_command_exact "Specode Loop request/response example verified." "$PROJECT_DIR" ./verify.sh
  assert_count "4" "$(count_file_matches '^## \[x\] Phase' "$PROJECT_DIR/plan.md")" "completed phase count"
  assert_count "0" "$(count_file_matches '^## \[ \] Phase' "$PROJECT_DIR/plan.md")" "remaining unchecked phase count"
  [[ -d "$PROJECT_DIR/.agents/skills/specode-do-work" ]] || fail "project-local specode-do-work skill was not copied"
  assert_file_contains "$PROJECT_DIR/.agents/skills/specode-do-work/SKILL.md" "name: specode-do-work"
  assert_path_missing "$PROJECT_DIR/.codex/skills/do-work"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "Bundled workflow skill synced: specode-do-work:$PROJECT_DIR/.agents/skills/specode-do-work"
  assert_count "4" "$(count_file_matches "TASK DONE sentinel detected" "$PROJECT_DIR/specode_loop.log")" "TASK DONE sentinel count"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "ALL TASKS DONE sentinel detected"
  assert_file_contains "$STDOUT_FILE" "Specode Loop preflight passed."
  assert_file_contains "$STDOUT_FILE" "ALL TASKS DONE sentinel detected"

  if keep_artifacts; then
    log "Python E2E artifacts kept at: $PROJECT_DIR"
    log "stdout transcript: $STDOUT_FILE"
    log "stderr transcript: $STDERR_FILE"
  fi

  log "Specode Loop Python real E2E passed."
}

main "$@"
