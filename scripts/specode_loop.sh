#!/usr/bin/env bash

set -euo pipefail

MAX_ITERATIONS="10"
MODEL=""
MODEL_REASONING_EFFORT=""
SPECODE_LOOP_VERBOSE="${SPECODE_LOOP_VERBOSE:-0}"
RUNNER_SKILLS_REL=".agents/skills"
SPECODE_WORKFLOW_SKILL="specode-do-work"
SPECODE_REQUIRED_SKILLS=(specode-do-work)
ACTIVE_SANDBOX=""
TEMP_OUTPUT=""
LAST_MESSAGE_OUTPUT=""
LOG_FILE=""
LAST_SENTINEL=""
FAILURE_EXCERPT_LINES=30

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

append_log_line() {
  if [[ -n "$LOG_FILE" ]]; then
    printf '%s\n' "$*" >>"$LOG_FILE"
  fi
}

report_cleanup_line() {
  local print_to_terminal="$1"
  local message="$2"

  if [[ "$print_to_terminal" == "1" ]]; then
    log_line "$message"
  else
    append_log_line "$message"
  fi
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
  local max_project_name_len=20

  project_name="$(sanitize_name_part "$(basename "$PROJECT_DIR_ABS")")"
  if [[ "${#project_name}" -gt "$max_project_name_len" ]]; then
    project_name="${project_name:0:$max_project_name_len}"
    project_name="${project_name%-}"
  fi
  if [[ -z "$project_name" ]]; then
    project_name="project"
  fi
  run_stamp="$(date '+%Y%m%d-%H%M%S')"

  printf 'specode-loop-%s-%s-%02d-%s\n' "$project_name" "$run_stamp" "$iteration" "$$"
}

cleanup_active_sandbox() {
  local print_to_terminal="${1:-0}"
  local report_no_active="${2:-0}"
  local sandbox_name
  local cleanup_status
  local cleanup_exit_code

  if [[ -n "$ACTIVE_SANDBOX" ]]; then
    sandbox_name="$ACTIVE_SANDBOX"
    if sbx rm "$sandbox_name" >/dev/null 2>&1; then
      cleanup_status="Sandbox cleanup: removed sandbox $sandbox_name."
    else
      cleanup_exit_code="$?"
      cleanup_status="Sandbox cleanup: failed to remove sandbox $sandbox_name (exit code: $cleanup_exit_code)."
    fi
    ACTIVE_SANDBOX=""
    report_cleanup_line "$print_to_terminal" "$cleanup_status"
  elif [[ "$report_no_active" == "1" ]]; then
    report_cleanup_line "$print_to_terminal" "Sandbox cleanup: no active sandbox to remove."
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

runner_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

sync_required_bundled_skills() {
  local source_root="$1/$RUNNER_SKILLS_REL"
  local target_root="$PROJECT_DIR_ABS/$RUNNER_SKILLS_REL"
  local skill_name source_dir target_dir
  local target_parent

  for skill_name in "${SPECODE_REQUIRED_SKILLS[@]}"; do
    source_dir="$source_root/$skill_name"
    target_dir="$target_root/$skill_name"
    target_parent="$(dirname "$target_dir")"

    [[ -d "$source_dir" ]] || fail "bundled workflow skill directory is missing: $source_dir"

    if [[ "$source_dir" == "$target_dir" ]]; then
      SYNCED_BUNDLED_SKILLS+=("$skill_name:$target_dir")
      continue
    fi

    mkdir -p "$target_parent"
    rm -rf "$target_dir"
    cp -R "$source_dir" "$target_dir"
    SYNCED_BUNDLED_SKILLS+=("$skill_name:$target_dir")
  done
}

build_prompt() {
  cat <<EOF
You are running non-interactively inside Docker Sandbox.

Project root:
$PROJECT_DIR_ABS

Use the project-local $SPECODE_WORKFLOW_SKILL skill.

Read prd.md and plan.md before choosing work.

Work on AFK Phases only. Do not work on HITL Phases.

Select exactly one undone AFK Phase in plan.md for this run.
Complete only the selected AFK Phase.
Mark the completed AFK Phase done in plan.md by changing its checkbox from "[ ]" to "[x]".

If no undone AFK Phases remain, output exactly:
$ALL_TASKS_DONE_SENTINEL

When the selected AFK Phase is complete and plan.md has been updated, output exactly:
$TASK_DONE_SENTINEL

Blocked or incomplete work must not output a success sentinel.
EOF
}

sentinel_detected() {
  local sentinel="$1"

  grep -Fxq "$sentinel" "$TEMP_OUTPUT" ||
    { [[ -s "$LAST_MESSAGE_OUTPUT" ]] && grep -Fxq "$sentinel" "$LAST_MESSAGE_OUTPUT"; }
}

print_no_sentinel_failure_summary() {
  local iteration="$1"
  local command_status="$2"
  local sandbox_name="$3"

  {
    printf '\n'
    printf 'Sandbox iteration failed without a success sentinel.\n'
    printf 'Iteration: %s/%s\n' "$iteration" "$MAX_ITERATIONS"
    printf 'Sandbox: %s\n' "$sandbox_name"
    printf 'Sandbox command exit code: %s\n' "$command_status"
    printf 'Expected success sentinels:\n'
    printf -- '- %s\n' "$TASK_DONE_SENTINEL"
    printf -- '- %s\n' "$ALL_TASKS_DONE_SENTINEL"
    printf 'Project log: %s\n' "$LOG_FILE"
    printf 'Last %s captured output lines:\n' "$FAILURE_EXCERPT_LINES"
    if [[ -s "$TEMP_OUTPUT" ]]; then
      tail -n "$FAILURE_EXCERPT_LINES" "$TEMP_OUTPUT"
    else
      printf '(no output captured)\n'
    fi
    printf 'For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1.\n'
  } | tee -a "$LOG_FILE"
}

print_max_iteration_stop_summary() {
  {
    printf '\n'
    printf 'Specode Loop stopped at the maximum iteration cap.\n'
    printf 'Configured maximum iterations reached: %s\n' "$MAX_ITERATIONS"
    printf 'Stop reason: reached max iterations (%s) before %s.\n' "$MAX_ITERATIONS" "$ALL_TASKS_DONE_SENTINEL"
    printf '%s was not observed.\n' "$ALL_TASKS_DONE_SENTINEL"
    printf 'Project log: %s\n' "$LOG_FILE"
  } | tee -a "$LOG_FILE"
}

run_single_task_iteration() {
  local iteration="$1"
  local -a codex_args
  local command_status
  local sandbox_name

  LAST_SENTINEL=""
  ACTIVE_SANDBOX="$(new_sandbox_name "$iteration")"
  sandbox_name="$ACTIVE_SANDBOX"
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
  print_no_sentinel_failure_summary "$iteration" "$command_status" "$sandbox_name"
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
RUNNER_ROOT="$(runner_root)"
SYNCED_BUNDLED_SKILLS=()

[[ -f "$PRD_ABS" ]] || fail "required PRD file is missing: $PRD_ABS"
[[ -f "$PLAN_ABS" ]] || fail "required plan file is missing: $PLAN_ABS"

warn_for_existing_git_state "$PROJECT_DIR_ABS"

sync_required_bundled_skills "$RUNNER_ROOT"
PROMPT="$(build_prompt)"

printf 'Specode Loop preflight passed.\n'
printf 'Project: %s\n' "$PROJECT_DIR_ABS"
printf 'Workspace mode: direct (sandbox edits apply to this working tree)\n'
printf 'PRD: %s\n' "$PRD_ABS"
printf 'Plan: %s\n' "$PLAN_ABS"
for synced_skill in "${SYNCED_BUNDLED_SKILLS[@]}"; do
  printf 'Bundled workflow skill synced: %s\n' "$synced_skill"
done
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
for synced_skill in "${SYNCED_BUNDLED_SKILLS[@]}"; do
  log_line "Bundled workflow skill synced: $synced_skill"
done
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

trap 'printf "\nInterrupted.\n" >&2; cleanup_temp_output; cleanup_active_sandbox 1 1; exit 130' INT TERM
trap 'cleanup_temp_output; cleanup_active_sandbox 0 0' EXIT

for ((iteration = 1; iteration <= MAX_ITERATIONS; iteration++)); do
  if run_single_task_iteration "$iteration"; then
    cleanup_active_sandbox 0 0

    if [[ "$LAST_SENTINEL" == "all" ]]; then
      exit 0
    fi

    continue
  fi

  cleanup_active_sandbox 1 0
  exit 1
done

print_max_iteration_stop_summary
exit 1
