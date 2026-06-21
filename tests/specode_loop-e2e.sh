#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/specode_loop.sh"
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

make_project() {
  PROJECT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode_loop-e2e.XXXXXX")"
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"

  cat >"$PROJECT_DIR/prd.md" <<'EOF'
# Specode Loop Real E2E PRD

## Goal

Verify Specode Loop can run a real sandboxed Codex task against a project with conventional documents.

## Desired Behavior

Create `artifact.txt` in this project with exactly this sentence:

Specode Loop real sandbox smoke test passed.

## Constraints

- Do not modify files outside this fixture project except Specode Loop's copied project-local skill configuration.
- Do not make a Git commit.
- Keep output deterministic and plain text.
EOF

  cat >"$PROJECT_DIR/plan.md" <<'EOF'
# Specode Loop Real E2E Plan

- [ ] Create `artifact.txt` containing exactly `Specode Loop real sandbox smoke test passed.`
EOF
}

main() {
  local -a args

  trap cleanup EXIT
  load_env

  command -v sbx >/dev/null 2>&1 || fail "sbx is not installed or not on PATH"

  make_project
  log "E2E project: $PROJECT_DIR"

  args=("$PROJECT_DIR" --max-iterations 2)
  if [[ -n "${SPECODE_LOOP_E2E_MODEL:-}" ]]; then
    args+=(--model "$SPECODE_LOOP_E2E_MODEL")
  fi

  if ! bash "$RUNNER" "${args[@]}"; then
    fail "runner exited before completing the e2e task"
  fi

  assert_file_exact "$PROJECT_DIR/artifact.txt" "Specode Loop real sandbox smoke test passed."
  assert_file_contains "$PROJECT_DIR/plan.md" "- [x] Create \`artifact.txt\`"
  [[ -d "$PROJECT_DIR/.agents/skills/specode-do-work" ]] || fail "project-local specode-do-work skill was not copied"
  assert_file_contains "$PROJECT_DIR/.agents/skills/specode-do-work/SKILL.md" "name: specode-do-work"
  assert_path_missing "$PROJECT_DIR/.codex/skills/do-work"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "Bundled workflow skill synced: specode-do-work:$PROJECT_DIR/.agents/skills/specode-do-work"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "TASK DONE sentinel detected"
  assert_file_contains "$PROJECT_DIR/specode_loop.log" "ALL TASKS DONE sentinel detected"

  if [[ -d "$PROJECT_DIR/.git" ]]; then
    assert_file_missing_or_empty "$PROJECT_DIR/.git/rebase-merge/interactive"
  fi

  log "Specode Loop real E2E passed."
}

main "$@"
