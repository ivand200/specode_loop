#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANONICAL_KIT="$ROOT_DIR/sandbox-kits/workflow-skills"
ENV_FILE="${SPECODE_LOOP_WORKFLOW_KIT_E2E_ENV:-${SPECODE_LOOP_E2E_ENV:-}}"
WORK_DIR=""
FAILED=0

KIT_MARKER="SPECODE_LOOP_E2E_KIT_SKILL_SELECTED"
DO_WORK_MARKER="SPECODE_LOOP_E2E_PROJECT_DO_WORK_SELECTED"
OVERRIDE_MARKER="SPECODE_LOOP_E2E_PROJECT_OVERRIDE_SELECTED"

log() {
  printf '%s\n' "$*"
}

keep_artifacts() {
  [[ "${SPECODE_LOOP_WORKFLOW_KIT_E2E_KEEP:-0}" == "1" || "${SPECODE_LOOP_KEEP_E2E_ARTIFACTS:-0}" == "1" ]]
}

fail() {
  FAILED=1
  printf 'Workflow Kit E2E failure: %s\n' "$*" >&2
  if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
    printf 'Artifacts left for inspection: %s\n' "$WORK_DIR" >&2
  fi
  exit 1
}

cleanup() {
  if [[ "$FAILED" != "1" ]] && ! keep_artifacts && [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
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

assert_contains() {
  local file="$1"
  local expected="$2"

  grep -Fq -- "$expected" "$file" || fail "expected $file to contain: $expected"
}

assert_not_contains() {
  local file="$1"
  local forbidden="$2"

  if grep -Fq -- "$forbidden" "$file"; then
    fail "expected $file not to contain: $forbidden"
  fi
}

sha256_file() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

write_project_manifest() {
  local project_dir="$1"
  local output_file="$2"

  python3 - "$project_dir" "$output_file" <<'PY'
import hashlib
import pathlib
import sys

project = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
rows = []
for path in sorted(item for item in project.rglob("*") if item.is_file()):
    if path.name == "specode_loop.log":
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.append(f"{path.relative_to(project).as_posix()}  {digest}\n")
output.write_text("".join(rows), encoding="utf-8")
PY
}

make_runner_copy() {
  local runner_root="$WORK_DIR/runner"
  local skill

  mkdir -p "$runner_root/scripts" "$runner_root/sandbox-kits"
  cp "$ROOT_DIR/scripts/specode_loop.py" "$runner_root/scripts/specode_loop.py"
  cp "$ROOT_DIR/scripts/specode_loop_iteration.py" "$runner_root/scripts/specode_loop_iteration.py"
  cp -R "$CANONICAL_KIT" "$runner_root/sandbox-kits/workflow-skills"

  skill="$runner_root/sandbox-kits/workflow-skills/files/home/.agents/skills/specode-loop-implement/SKILL.md"
  cat >>"$skill" <<EOF

## Real E2E selection evidence

For this instrumented E2E only, verify that the Target Project's
\`.agents/skills/do-work/SKILL.md\` is readable when it exists, but do not invoke
that unrelated skill. When no undone AFK Plan Task remains, make the final
message contain these two exact lines and no project-skill marker:

$KIT_MARKER
ALL TASKS DONE
EOF
}

make_project() {
  local project_dir="$1"
  local kind="$2"
  local skill_dir

  mkdir -p "$project_dir/.agents/skills"
  cat >"$project_dir/prd.md" <<'EOF'
# PRD: Workflow Skill Selection E2E

Prove which implementation workflow skill Codex selects in a real Docker
Sandbox without changing the Target Project.
EOF
  cat >"$project_dir/plan.md" <<'EOF'
# Plan: Workflow Skill Selection E2E

## [x] 1. Already complete

**Type:** AFK

No project changes are required. Report that all tasks are done.
EOF

  if [[ "$kind" == "default" ]]; then
    skill_dir="$project_dir/.agents/skills/do-work"
    mkdir -p "$skill_dir"
    cat >"$skill_dir/SKILL.md" <<EOF
---
name: do-work
description: "Unrelated project workflow used only as a real E2E decoy."
---

If invoked, include this exact marker in the final message:
$DO_WORK_MARKER
EOF
  else
    skill_dir="$project_dir/.agents/skills/specode-loop-implement"
    mkdir -p "$skill_dir"
    cat >"$skill_dir/SKILL.md" <<EOF
---
name: specode-loop-implement
description: "Deliberate project override used by the real precedence E2E."
---

When no undone AFK Plan Task remains, make the final message contain these two
exact lines and no kit marker:

$OVERRIDE_MARKER
ALL TASKS DONE
EOF
  fi
}

assert_sandbox_absent() {
  local project_log="$1"
  local listing_file="$2"
  local sandbox_name

  sandbox_name="$(sed -n 's/^Sandbox cleanup: removed sandbox \([^.]\{1,\}\)\.$/\1/p' "$project_log")"
  [[ -n "$sandbox_name" ]] || fail "could not extract the sandbox name from cleanup evidence"
  [[ "$(printf '%s\n' "$sandbox_name" | wc -l | tr -d ' ')" == "1" ]] || fail "expected exactly one cleanup sandbox name"

  sbx ls --json >"$listing_file" || fail "sbx ls --json failed"
  if grep -Fq -- "$sandbox_name" "$listing_file"; then
    fail "sandbox still appears in sbx ls --json: $sandbox_name"
  fi
}

run_case() {
  local kind="$1"
  local expected_marker="$2"
  local forbidden_marker="$3"
  local project_dir="$WORK_DIR/project-$kind"
  local stdout_file="$WORK_DIR/$kind.stdout"
  local stderr_file="$WORK_DIR/$kind.stderr"
  local before_manifest="$WORK_DIR/$kind.before.sha256"
  local after_manifest="$WORK_DIR/$kind.after.sha256"
  local listing_file="$WORK_DIR/$kind.sbx-list.json"
  local project_skill
  local project_skill_hash
  local -a args

  make_project "$project_dir" "$kind"
  if [[ "$kind" == "default" ]]; then
    project_skill="$project_dir/.agents/skills/do-work/SKILL.md"
  else
    project_skill="$project_dir/.agents/skills/specode-loop-implement/SKILL.md"
  fi
  project_skill_hash="$(sha256_file "$project_skill")"
  write_project_manifest "$project_dir" "$before_manifest"

  args=("$project_dir" --max-iterations 1)
  args+=(--auth "${SPECODE_LOOP_WORKFLOW_KIT_E2E_AUTH:-${SPECODE_LOOP_E2E_AUTH:-oauth}}")
  if [[ -n "${SPECODE_LOOP_WORKFLOW_KIT_E2E_MODEL:-${SPECODE_LOOP_E2E_MODEL:-}}" ]]; then
    args+=(--model "${SPECODE_LOOP_WORKFLOW_KIT_E2E_MODEL:-${SPECODE_LOOP_E2E_MODEL:-}}")
  fi

  if ! SPECODE_LOOP_VERBOSE=1 python3 "$WORK_DIR/runner/scripts/specode_loop.py" "${args[@]}" >"$stdout_file" 2>"$stderr_file"; then
    sed -n '1,260p' "$stdout_file" >&2 || true
    sed -n '1,260p' "$stderr_file" >&2 || true
    fail "$kind runner invocation did not exit successfully"
  fi

  assert_contains "$stdout_file" "$expected_marker"
  assert_not_contains "$stdout_file" "$forbidden_marker"
  assert_contains "$stdout_file" "ALL TASKS DONE sentinel detected"
  assert_contains "$project_dir/specode_loop.log" "$expected_marker"
  assert_not_contains "$project_dir/specode_loop.log" "$forbidden_marker"
  assert_contains "$project_dir/specode_loop.log" "Workflow kit validated: $WORK_DIR/runner/sandbox-kits/workflow-skills"

  [[ "$(sha256_file "$project_skill")" == "$project_skill_hash" ]] || fail "$kind project-owned skill changed"
  [[ ! -e "$project_dir/.specode_loop-last-message.1.$$" ]] || fail "$kind attempt final-message artifact remains"
  if find "$project_dir" -name '.specode_loop-last-message.*' -print -quit | grep -q .; then
    fail "$kind attempt final-message artifact remains"
  fi
  if [[ "$kind" == "default" && -e "$project_dir/.agents/skills/specode-loop-implement" ]]; then
    fail "the service implementation skill was provisioned into the default Target Project"
  fi

  write_project_manifest "$project_dir" "$after_manifest"
  cmp -s "$before_manifest" "$after_manifest" || fail "$kind Target Project changed beyond specode_loop.log"
  assert_sandbox_absent "$project_dir/specode_loop.log" "$listing_file"
  log "Workflow Kit E2E case passed: $kind"
}

main() {
  trap cleanup EXIT
  load_env

  command -v sbx >/dev/null 2>&1 || fail "sbx is not installed or not on PATH"
  command -v python3 >/dev/null 2>&1 || fail "python3 is not installed or not on PATH"

  WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode-loop-workflow-kit-e2e.XXXXXX")"
  WORK_DIR="$(cd "$WORK_DIR" && pwd -P)"
  make_runner_copy

  run_case default "$KIT_MARKER" "$DO_WORK_MARKER"
  run_case override "$OVERRIDE_MARKER" "$KIT_MARKER"

  if keep_artifacts; then
    log "Workflow Kit E2E artifacts kept at: $WORK_DIR"
  fi
  log "Specode Loop Workflow Kit real E2E passed."
}

main "$@"
