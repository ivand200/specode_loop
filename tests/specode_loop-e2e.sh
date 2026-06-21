#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/specode_loop.sh"
EXAMPLE_PROJECT="$ROOT_DIR/examples/basic"
ENV_FILE="${SPECODE_LOOP_E2E_ENV:-}"
PROJECT_DIR=""

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'E2E failure: %s\n' "$*" >&2
  if [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
    printf 'Project left for inspection: %s\n' "$PROJECT_DIR" >&2
  fi
  exit 1
}

cleanup() {
  if [[ "${SPECODE_LOOP_E2E_KEEP:-0}" != "1" && -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
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

assert_command_exact() {
  local expected="$1"
  shift
  local actual

  actual="$("$@")" || fail "expected command to succeed: $*"
  [[ "$actual" == "$expected" ]] || fail "expected command output exactly: $expected"
}

assert_project_command_exact() {
  local expected="$1"
  local project_dir="$2"
  shift 2
  local actual

  actual="$(cd "$project_dir" && "$@")" || fail "expected project command to succeed: $*"
  [[ "$actual" == "$expected" ]] || fail "expected project command output exactly: $expected"
}

assert_file_missing_or_empty() {
  local file="$1"

  if [[ -s "$file" ]]; then
    fail "expected $file to be empty or absent"
  fi
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
  PROJECT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode_loop-e2e.XXXXXX")"
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"

  cp -R "$EXAMPLE_PROJECT/." "$PROJECT_DIR"
}

main() {
  local -a args

  trap cleanup EXIT
  load_env

  command -v sbx >/dev/null 2>&1 || fail "sbx is not installed or not on PATH"

  make_project
  log "E2E project: $PROJECT_DIR"

  args=("$PROJECT_DIR" --max-iterations 4)
  if [[ -n "${SPECODE_LOOP_E2E_MODEL:-}" ]]; then
    args+=(--model "$SPECODE_LOOP_E2E_MODEL")
  fi

  if ! bash "$RUNNER" "${args[@]}"; then
    fail "runner exited before completing the e2e task"
  fi

  assert_file_contains "$PROJECT_DIR/prd.md" "## Problem Statement"
  assert_file_contains "$PROJECT_DIR/prd.md" "## User Stories"
  assert_file_contains "$PROJECT_DIR/prd.md" "## Implementation Decisions"
  assert_file_contains "$PROJECT_DIR/prd.md" "## Testing Decisions"
  assert_file_contains "$PROJECT_DIR/plan.md" "# Plan: Specode Loop Example Acceptance Fixture"
  assert_file_contains "$PROJECT_DIR/plan.md" "> Source PRD: prd.md"
  assert_file_contains "$PROJECT_DIR/plan.md" "## Architectural decisions"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 1: Artifact Status Trail"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 2: Derived Summary"
  assert_file_contains "$PROJECT_DIR/plan.md" "## [x] Phase 3: Executable Verification"
  assert_file_contains "$PROJECT_DIR/plan.md" "### Acceptance criteria"
  assert_file_contains "$PROJECT_DIR/plan.md" "## Blocked by"
  assert_file_exact "$PROJECT_DIR/artifact.txt" $'Specode Loop example task 1 complete.\nSpecode Loop example task 2 complete.'
  assert_file_exact "$PROJECT_DIR/summary.md" $'# Specode Loop Example Summary\n\n- Task 1: Specode Loop example task 1 complete.\n- Task 2: Specode Loop example task 2 complete.'
  assert_executable "$PROJECT_DIR/verify.sh"
  assert_project_command_exact "Specode Loop example verified." "$PROJECT_DIR" ./verify.sh
  assert_count "3" "$(count_file_matches '^## \[x\] Phase' "$PROJECT_DIR/plan.md")" "completed phase count"
  assert_count "0" "$(count_file_matches '^## \[ \] Phase' "$PROJECT_DIR/plan.md")" "remaining unchecked phase count"
  [[ -d "$PROJECT_DIR/.agents/skills/specode-do-work" ]] || fail "project-local specode-do-work skill was not copied"
  assert_file_contains "$PROJECT_DIR/.agents/skills/specode-do-work/SKILL.md" "name: specode-do-work"
  assert_path_missing "$PROJECT_DIR/.codex/skills/do-work"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "Bundled workflow skill synced: specode-do-work:$PROJECT_DIR/.agents/skills/specode-do-work"
  assert_count "3" "$(count_file_matches "TASK DONE sentinel detected" "$PROJECT_DIR/specode_loop.log")" "TASK DONE sentinel count"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "ALL TASKS DONE sentinel detected"

  if [[ -d "$PROJECT_DIR/.git" ]]; then
    assert_file_missing_or_empty "$PROJECT_DIR/.git/rebase-merge/interactive"
  fi

  log "Specode Loop real E2E passed."
}

main "$@"
