#!/usr/bin/env bash

set -euo pipefail

MAX_ITERATIONS="10"
MODEL=""
MODEL_REASONING_EFFORT=""
SPECODE_LOOP_VERBOSE="${SPECODE_LOOP_VERBOSE:-0}"
PROJECT_DO_WORK_SKILL_REL=".codex/skills/do-work"
ACTIVE_SANDBOX=""
TEMP_OUTPUT=""
LAST_MESSAGE_OUTPUT=""
LOG_FILE=""
LAST_SENTINEL=""

TASK_DONE_SENTINEL="TASK DONE"
ALL_TASKS_DONE_SENTINEL="ALL TASKS DONE"

usage() {
  cat <<'EOF'
Usage: scripts/specode_loop.sh PROJECT_DIR [options]

Run Specode Loop for a project with conventional planning documents.

Arguments:
  PROJECT_DIR              Project directory containing prd.md and plan.md

Options:
  --max-iterations N       Maximum sandbox iterations to run (default: 10)
  --model MODEL            Optional model for the sandboxed Codex run
  --effort EFFORT          Optional reasoning effort: minimal, low, medium, high, xhigh
  --reasoning-effort EFFORT
                           Alias for --effort
  -h, --help               Show this help
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'Warning: %s\n' "$*" >&2
}

log_line() {
  printf '%s\n' "$*" | tee -a "$LOG_FILE"
}

is_verbose_log() {
  [[ "$SPECODE_LOOP_VERBOSE" == "1" ]]
}

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %z'
}

sanitize_name_part() {
  local value="$1"

  value="${value//[^[:alnum:]]/-}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  value="${value#-}"
  value="${value%-}"

  if [[ -z "$value" ]]; then
    value="project"
  fi

  printf '%s\n' "$value"
}

new_sandbox_name() {
  local iteration="$1"
  local project_name
  local run_stamp

  project_name="$(sanitize_name_part "$(basename "$PROJECT_DIR_ABS")")"
  run_stamp="$(date '+%Y%m%d-%H%M%S')"

  printf 'specode_loop-%s-%s-%02d-%s\n' "$project_name" "$run_stamp" "$iteration" "$$"
}

cleanup_active_sandbox() {
  if [[ -n "$ACTIVE_SANDBOX" ]]; then
    if [[ -n "$LOG_FILE" ]]; then
      log_line "Removing sandbox: $ACTIVE_SANDBOX"
    fi
    sbx rm "$ACTIVE_SANDBOX" >/dev/null 2>&1 || true
    ACTIVE_SANDBOX=""
  fi
}

cleanup_temp_output() {
  if [[ -n "$TEMP_OUTPUT" && -f "$TEMP_OUTPUT" ]]; then
    rm -f "$TEMP_OUTPUT"
    TEMP_OUTPUT=""
  fi

  if [[ -n "$LAST_MESSAGE_OUTPUT" && -f "$LAST_MESSAGE_OUTPUT" ]]; then
    rm -f "$LAST_MESSAGE_OUTPUT"
    LAST_MESSAGE_OUTPUT=""
  fi
}

validate_positive_integer() {
  local name="$1"
  local value="$2"

  [[ "$value" =~ ^[1-9][0-9]*$ ]] || fail "$name must be a positive integer"
}

validate_reasoning_effort() {
  local value="$1"

  if [[ -z "$value" ]]; then
    return
  fi

  case "$value" in
    minimal|low|medium|high|xhigh)
      ;;
    *)
      fail "--effort must be one of: minimal, low, medium, high, xhigh"
      ;;
  esac
}

warn_for_existing_git_state() {
  local project_dir="$1"
  local has_unstaged_changes=0

  if ! git -C "$project_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "$project_dir is not inside a Git work tree. Continuing."
    return
  fi

  if ! git -C "$project_dir" diff --quiet --ignore-submodules -- 2>/dev/null; then
    has_unstaged_changes=1
  fi

  if [[ -n "$(git -C "$project_dir" ls-files --others --exclude-standard 2>/dev/null)" ]]; then
    has_unstaged_changes=1
  fi

  if [[ "$has_unstaged_changes" -eq 1 ]]; then
    warn "$project_dir has existing unstaged changes. Continuing."
  fi

  if ! git -C "$project_dir" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
    warn "$project_dir has existing staged changes. Continuing."
  fi
}

global_do_work_skill_path() {
  local codex_home

  if [[ -n "${CODEX_HOME:-}" ]]; then
    codex_home="$CODEX_HOME"
  else
    codex_home="$HOME/.codex"
  fi

  printf '%s/skills/do-work\n' "$codex_home"
}

sync_do_work_skill() {
  local source_dir="$1"
  local target_dir="$PROJECT_DIR_ABS/$PROJECT_DO_WORK_SKILL_REL"
  local target_parent

  [[ -d "$source_dir" ]] || fail "global do-work skill directory is missing: $source_dir"

  target_parent="$(dirname "$target_dir")"
  mkdir -p "$target_parent"
  rm -rf "$target_dir"
  cp -R "$source_dir" "$target_dir"
}

build_prompt() {
  cat <<EOF
You are running inside a Docker Sandbox. The sandbox is the safety boundary, and this is a non-interactive automation run.

Project root:
$PROJECT_DIR_ABS

Project documents:
- PRD: prd.md
- Plan: plan.md

Required workflow:
- Use the project-local do-work skill for this task.
- Treat $PROJECT_DO_WORK_SKILL_REL as runner configuration copied in by Specode Loop.
- Do not modify $PROJECT_DO_WORK_SKILL_REL as part of task work.
- Read both project documents before choosing work.
- Select exactly first one undone Markdown checkbox task in plan.md for this run.
- Use the first undone task unless plan.md gives explicit priority rules.
- If there are no undone tasks in plan.md, output exactly the full line "$ALL_TASKS_DONE_SENTINEL" and do no task work.
- Complete only the selected task.
- Mark the completed task done in plan.md by changing its checkbox from "- [ ]" to "- [x]".
- Work directly in the project working tree; Docker Sandbox direct workspace mode makes those changes visible on the host.
- Do not make a git commit unless prd.md or plan.md explicitly requires it.
- When the selected task is complete and plan.md has been updated, output exactly the full line "$TASK_DONE_SENTINEL".
- Do not output "$TASK_DONE_SENTINEL" unless the selected task is complete and plan.md was updated.
- Do not output "$ALL_TASKS_DONE_SENTINEL" unless no undone checkbox tasks remain.
- Blocked or incomplete work must not output a success sentinel.
EOF
}

sentinel_detected() {
  local sentinel="$1"

  grep -Fxq "$sentinel" "$TEMP_OUTPUT" ||
    { [[ -s "$LAST_MESSAGE_OUTPUT" ]] && grep -Fxq "$sentinel" "$LAST_MESSAGE_OUTPUT"; }
}

run_single_task_iteration() {
  local iteration="$1"
  local -a codex_args
  local command_status

  LAST_SENTINEL=""
  ACTIVE_SANDBOX="$(new_sandbox_name "$iteration")"
  TEMP_OUTPUT="$(mktemp "${TMPDIR:-/tmp}/specode_loop.${iteration}.XXXXXX")"
  LAST_MESSAGE_OUTPUT="$PROJECT_DIR_ABS/.specode_loop-last-message.${iteration}.$$"
  codex_args=(exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C "$PROJECT_DIR_ABS")

  if [[ -n "$MODEL" ]]; then
    codex_args+=(-m "$MODEL")
  fi

  if [[ -n "$MODEL_REASONING_EFFORT" ]]; then
    codex_args+=(-c "model_reasoning_effort=\"$MODEL_REASONING_EFFORT\"")
  fi

  codex_args+=(-o "$LAST_MESSAGE_OUTPUT")
  codex_args+=("$PROMPT")
  rm -f "$LAST_MESSAGE_OUTPUT"

  log_line ""
  log_line "===== Specode Loop iteration $iteration/$MAX_ITERATIONS | $(timestamp) | sandbox: $ACTIVE_SANDBOX ====="
  log_line "Starting non-interactive Codex run in Docker Sandbox direct workspace mode."

  set +e
  if is_verbose_log; then
    sbx run --name "$ACTIVE_SANDBOX" codex "$PROJECT_DIR_ABS" -- "${codex_args[@]}" 2>&1 | tee -a "$LOG_FILE" | tee "$TEMP_OUTPUT"
    command_status=${PIPESTATUS[0]}
  else
    sbx run --name "$ACTIVE_SANDBOX" codex "$PROJECT_DIR_ABS" -- "${codex_args[@]}" 2>&1 | tee "$TEMP_OUTPUT"
    command_status=${PIPESTATUS[0]}
  fi
  set -e

  if [[ -s "$LAST_MESSAGE_OUTPUT" ]]; then
    if is_verbose_log; then
      log_line "===== Codex final message captured from --output-last-message ====="
      {
        cat "$LAST_MESSAGE_OUTPUT"
        printf '\n'
      } | tee -a "$LOG_FILE" | tee -a "$TEMP_OUTPUT"
    else
      log_line "Captured Codex final message from --output-last-message."
      cat "$LAST_MESSAGE_OUTPUT" >>"$TEMP_OUTPUT"
      printf '\n' >>"$TEMP_OUTPUT"
    fi
  fi

  if sentinel_detected "$ALL_TASKS_DONE_SENTINEL"; then
    log_line "===== iteration $iteration status: ALL TASKS DONE sentinel detected; overall run complete (command exit code: $command_status) ====="
    LAST_SENTINEL="all"
    cleanup_temp_output
    return 0
  fi

  if sentinel_detected "$TASK_DONE_SENTINEL"; then
    log_line "===== iteration $iteration status: TASK DONE sentinel detected; iteration successful (command exit code: $command_status) ====="
    LAST_SENTINEL="task"
    cleanup_temp_output
    return 0
  fi

  log_line "===== iteration $iteration status: FAILED, no exact success sentinel detected (command exit code: $command_status) ====="
  LAST_SENTINEL="none"
  cleanup_temp_output
  return 1
}

parse_args() {
  if [[ $# -eq 0 ]]; then
    usage >&2
    exit 2
  fi

  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      fail "project directory is required as the first argument"
      ;;
    *)
      PROJECT_DIR="$1"
      shift
      ;;
  esac

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --max-iterations)
        [[ $# -ge 2 ]] || fail "--max-iterations requires a value"
        MAX_ITERATIONS="$2"
        shift 2
        ;;
      --model)
        [[ $# -ge 2 ]] || fail "--model requires a value"
        MODEL="$2"
        shift 2
        ;;
      --effort|--reasoning-effort)
        [[ $# -ge 2 ]] || fail "$1 requires a value"
        MODEL_REASONING_EFFORT="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "unknown argument: $1"
        ;;
    esac
  done
}

parse_args "$@"
validate_positive_integer "--max-iterations" "$MAX_ITERATIONS"
validate_reasoning_effort "$MODEL_REASONING_EFFORT"

command -v sbx >/dev/null 2>&1 || fail "Docker Sandbox CLI 'sbx' is not installed or not on PATH"

PROJECT_DIR_ABS="$(cd "$PROJECT_DIR" 2>/dev/null && pwd)" || fail "project directory does not exist: $PROJECT_DIR"
PRD_ABS="$PROJECT_DIR_ABS/prd.md"
PLAN_ABS="$PROJECT_DIR_ABS/plan.md"
LOG_FILE="$PROJECT_DIR_ABS/specode_loop.log"

[[ -f "$PRD_ABS" ]] || fail "required PRD file is missing: $PRD_ABS"
[[ -f "$PLAN_ABS" ]] || fail "required plan file is missing: $PLAN_ABS"

warn_for_existing_git_state "$PROJECT_DIR_ABS"

GLOBAL_DO_WORK_SKILL="$(global_do_work_skill_path)"
sync_do_work_skill "$GLOBAL_DO_WORK_SKILL"
PROMPT="$(build_prompt)"

printf 'Specode Loop preflight passed.\n'
printf 'Project: %s\n' "$PROJECT_DIR_ABS"
printf 'Workspace mode: direct (sandbox edits apply to this working tree)\n'
printf 'PRD: %s\n' "$PRD_ABS"
printf 'Plan: %s\n' "$PLAN_ABS"
printf 'do-work skill: %s -> %s\n' "$GLOBAL_DO_WORK_SKILL" "$PROJECT_DIR_ABS/$PROJECT_DO_WORK_SKILL_REL"
printf 'Max iterations: %s\n' "$MAX_ITERATIONS"
if [[ -n "$MODEL" ]]; then
  printf 'Model: %s\n' "$MODEL"
else
  printf 'Model: Codex/project default\n'
fi
if [[ -n "$MODEL_REASONING_EFFORT" ]]; then
  printf 'Reasoning effort: %s\n' "$MODEL_REASONING_EFFORT"
else
  printf 'Reasoning effort: Codex/project default\n'
fi

log_line "Specode Loop preflight passed."
log_line "Project: $PROJECT_DIR_ABS"
log_line "Workspace mode: direct (sandbox edits apply to this working tree)"
log_line "PRD: $PRD_ABS"
log_line "Plan: $PLAN_ABS"
log_line "do-work skill synced into project-local runner config."
log_line "Verbose transcript logging: $SPECODE_LOOP_VERBOSE"
log_line "Max iterations: $MAX_ITERATIONS"
if [[ -n "$MODEL" ]]; then
  log_line "Model: $MODEL"
else
  log_line "Model: Codex/project default"
fi
if [[ -n "$MODEL_REASONING_EFFORT" ]]; then
  log_line "Reasoning effort: $MODEL_REASONING_EFFORT"
else
  log_line "Reasoning effort: Codex/project default"
fi

trap 'printf "\nInterrupted.\n" >&2; cleanup_temp_output; cleanup_active_sandbox; exit 130' INT TERM
trap 'cleanup_temp_output; cleanup_active_sandbox' EXIT

for ((iteration = 1; iteration <= MAX_ITERATIONS; iteration++)); do
  if run_single_task_iteration "$iteration"; then
    cleanup_active_sandbox

    if [[ "$LAST_SENTINEL" == "all" ]]; then
      exit 0
    fi

    continue
  fi

  cleanup_active_sandbox
  exit 1
done

log_line "===== loop stopped: reached max iterations ($MAX_ITERATIONS) before ALL TASKS DONE ====="
exit 1
