#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/scripts/specode_loop.sh"

PASS_COUNT=0
FAIL_COUNT=0
CURRENT_TEST_DIR=""

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf 'ok - %s\n' "$1"
}

fail_test() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf 'not ok - %s\n' "$1" >&2
}

assert_status() {
  local expected="$1"
  local actual="$2"

  if [[ "$actual" -ne "$expected" ]]; then
    printf 'expected status %s, got %s\n' "$expected" "$actual" >&2
    return 1
  fi
}

assert_success() {
  local actual="$1"

  if [[ "$actual" -ne 0 ]]; then
    printf 'expected success, got status %s\n' "$actual" >&2
    return 1
  fi
}

assert_failure() {
  local actual="$1"

  if [[ "$actual" -eq 0 ]]; then
    printf 'expected failure, got success\n' >&2
    return 1
  fi
}

assert_file_contains() {
  local file="$1"
  local needle="$2"

  if ! grep -Fq -- "$needle" "$file"; then
    printf 'expected %s to contain: %s\n' "$file" "$needle" >&2
    printf '%s contents:\n' "$file" >&2
    sed -n '1,160p' "$file" >&2 || true
    return 1
  fi
}

assert_file_not_contains() {
  local file="$1"
  local needle="$2"

  if grep -Fq -- "$needle" "$file"; then
    printf 'expected %s not to contain: %s\n' "$file" "$needle" >&2
    printf '%s contents:\n' "$file" >&2
    sed -n '1,160p' "$file" >&2 || true
    return 1
  fi
}

assert_path_exists() {
  local path="$1"

  if [[ ! -e "$path" ]]; then
    printf 'expected path to exist: %s\n' "$path" >&2
    return 1
  fi
}

assert_path_missing() {
  local path="$1"

  if [[ -e "$path" ]]; then
    printf 'expected path to be absent: %s\n' "$path" >&2
    return 1
  fi
}

assert_no_paths_matching() {
  local pattern="$1"

  if compgen -G "$pattern" >/dev/null; then
    printf 'expected no paths matching: %s\n' "$pattern" >&2
    return 1
  fi
}

assert_equals() {
  local expected="$1"
  local actual="$2"

  if [[ "$actual" != "$expected" ]]; then
    printf 'expected %q, got %q\n' "$expected" "$actual" >&2
    return 1
  fi
}

make_test_dir() {
  CURRENT_TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode_loop-test.XXXXXX")"
  mkdir -p "$CURRENT_TEST_DIR/bin" "$CURRENT_TEST_DIR/codex-home/skills/do-work" "$CURRENT_TEST_DIR/scenarios"
  printf 'global skill\n' >"$CURRENT_TEST_DIR/codex-home/skills/do-work/SKILL.md"
  mkdir -p "$CURRENT_TEST_DIR/codex-home/skills/do-work/references"
  printf 'reference asset\n' >"$CURRENT_TEST_DIR/codex-home/skills/do-work/references/workflow.txt"
  install_fake_sbx "$CURRENT_TEST_DIR/bin/sbx"
}

cleanup_test_dir() {
  if [[ -n "$CURRENT_TEST_DIR" && -d "$CURRENT_TEST_DIR" ]]; then
    rm -rf "$CURRENT_TEST_DIR"
    CURRENT_TEST_DIR=""
  fi
}

install_fake_sbx() {
  local target="$1"

  cat >"$target" <<'EOF'
#!/usr/bin/env bash
set -u

cmd="${1:-}"
shift || true

case "$cmd" in
  run)
    name=""
    if [[ "${1:-}" == "--name" ]]; then
      name="${2:-}"
      shift 2
    fi

    count_file="$FAKE_SBX_DIR/count"
    count=0
    if [[ -f "$count_file" ]]; then
      count="$(cat "$count_file")"
    fi
    count=$((count + 1))
    printf '%s\n' "$count" >"$count_file"
    printf 'run|%s|%s\n' "$name" "$*" >>"$FAKE_SBX_DIR/calls.log"

    output_file="$FAKE_SBX_DIR/run_${count}.out"
    status_file="$FAKE_SBX_DIR/run_${count}.status"
    interrupt_file="$FAKE_SBX_DIR/run_${count}.interrupt"
    last_message_file="$FAKE_SBX_DIR/run_${count}.last"

    if [[ -f "$output_file" ]]; then
      cat "$output_file"
    fi

    if [[ -f "$last_message_file" ]]; then
      output_path=""
      previous=""
      for arg in "$@"; do
        if [[ "$previous" == "-o" ]]; then
          output_path="$arg"
          break
        fi
        previous="$arg"
      done

      if [[ -n "$output_path" ]]; then
        cat "$last_message_file" >"$output_path"
      fi
    fi

    if [[ -f "$interrupt_file" ]]; then
      kill -TERM "$PPID"
      sleep 0.1
      exit 143
    fi

    if [[ -f "$status_file" ]]; then
      exit "$(cat "$status_file")"
    fi

    exit 0
    ;;
  rm)
    printf 'rm|%s\n' "${1:-}" >>"$FAKE_SBX_DIR/rm.log"
    exit 0
    ;;
  *)
    printf 'unexpected fake sbx command: %s\n' "$cmd" >&2
    exit 127
    ;;
esac
EOF
  chmod +x "$target"
}

make_project() {
  local name="$1"
  local project="$CURRENT_TEST_DIR/$name"

  mkdir -p "$project"
  printf '# PRD\n' >"$project/prd.md"
  printf '# Plan\n\n- [ ] Do one task\n' >"$project/plan.md"
  (cd "$project" && pwd)
}

scenario() {
  local run_number="$1"
  local status="$2"
  local output="$3"

  printf '%s\n' "$output" >"$CURRENT_TEST_DIR/scenarios/run_${run_number}.out"
  printf '%s\n' "$status" >"$CURRENT_TEST_DIR/scenarios/run_${run_number}.status"
}

last_message() {
  local run_number="$1"
  local output="$2"

  printf '%s' "$output" >"$CURRENT_TEST_DIR/scenarios/run_${run_number}.last"
}

interrupt_scenario() {
  local run_number="$1"
  local output="$2"

  printf '%s\n' "$output" >"$CURRENT_TEST_DIR/scenarios/run_${run_number}.out"
  printf 'interrupt\n' >"$CURRENT_TEST_DIR/scenarios/run_${run_number}.interrupt"
}

run_loop() {
  local project="$1"
  shift

  PATH="$CURRENT_TEST_DIR/bin:$PATH" \
    CODEX_HOME="$CURRENT_TEST_DIR/codex-home" \
    FAKE_SBX_DIR="$CURRENT_TEST_DIR/scenarios" \
    SPECODE_LOOP_VERBOSE="${SPECODE_LOOP_VERBOSE:-}" \
    bash "$RUNNER" "$project" "$@" \
    >"$CURRENT_TEST_DIR/stdout" 2>"$CURRENT_TEST_DIR/stderr"
}

run_case() {
  local name="$1"
  shift

  make_test_dir
  if "$@"; then
    pass "$name"
  else
    fail_test "$name"
  fi
  cleanup_test_dir
}

test_missing_documents_and_max_validation() {
  local project status

  project="$CURRENT_TEST_DIR/missing-prd"
  mkdir -p "$project"
  printf '# Plan\n' >"$project/plan.md"
  run_loop "$project"
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "required PRD file is missing" || return 1

  project="$CURRENT_TEST_DIR/missing-plan"
  mkdir -p "$project"
  printf '# PRD\n' >"$project/prd.md"
  run_loop "$project"
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "required plan file is missing" || return 1

  project="$(make_project invalid-max)"
  run_loop "$project" --max-iterations 0
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "--max-iterations must be a positive integer" || return 1

  project="$(make_project invalid-effort)"
  run_loop "$project" --effort enormous
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "--effort must be one of: minimal, low, medium, high, xhigh" || return 1
}

test_skill_copy_and_overwrite() {
  local project status copied_skill copied_reference

  project="$(make_project skill-copy)"
  copied_skill="$project/.codex/skills/do-work/SKILL.md"
  copied_reference="$project/.codex/skills/do-work/references/workflow.txt"
  mkdir -p "$project/.codex/skills/do-work"
  printf 'stale local skill\n' >"$copied_skill"

  scenario 1 0 "ALL TASKS DONE"
  run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$copied_skill" "global skill" || return 1
  assert_file_not_contains "$copied_skill" "stale local skill" || return 1
  assert_file_contains "$copied_reference" "reference asset" || return 1
  assert_path_exists "$project/.codex/skills/do-work" || return 1
}

test_missing_global_skill_fails_before_sandbox() {
  local project status

  project="$(make_project missing-skill)"
  rm -rf "$CURRENT_TEST_DIR/codex-home/skills/do-work"

  run_loop "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "global do-work skill directory is missing" || return 1
  assert_path_missing "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1
}

test_dirty_git_warning() {
  local project status

  project="$(make_project dirty-git)"
  git -C "$project" init -q || return 1
  git -C "$project" config user.email test@example.com || return 1
  git -C "$project" config user.name "Test User" || return 1
  git -C "$project" add prd.md plan.md || return 1
  git -C "$project" commit -q -m initial || return 1
  printf 'changed\n' >>"$project/prd.md"
  printf 'staged\n' >"$project/staged.txt"
  git -C "$project" add staged.txt || return 1

  scenario 1 0 "ALL TASKS DONE"
  run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "existing unstaged changes" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "existing staged changes" || return 1
}

test_exact_sentinels_and_nonzero_override() {
  local project status

  project="$(make_project sentinel-flow)"
  scenario 1 42 "TASK DONE"
  scenario 2 42 "ALL TASKS DONE"

  run_loop "$project" --max-iterations 3
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "TASK DONE sentinel detected; iteration successful (command exit code: 42)" || return 1
  assert_file_contains "$project/specode_loop.log" "ALL TASKS DONE sentinel detected; overall run complete (command exit code: 42)" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode_loop-sentinel-flow-" || return 1
  assert_equals "2" "$(wc -l <"$CURRENT_TEST_DIR/scenarios/rm.log" | tr -d ' ')" || return 1
}

test_last_message_sentinel_detection() {
  local project status

  project="$(make_project last-message)"
  scenario 1 0 "agent stream without sentinel"
  last_message 1 "TASK DONE"
  scenario 2 0 "second stream without sentinel"
  last_message 2 "ALL TASKS DONE"

  run_loop "$project" --max-iterations 2
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "Captured Codex final message from --output-last-message" || return 1
  assert_file_contains "$project/specode_loop.log" "TASK DONE sentinel detected" || return 1
  assert_file_contains "$project/specode_loop.log" "ALL TASKS DONE sentinel detected" || return 1
  assert_no_paths_matching "$project/.specode_loop-last-message.*" || return 1
}

test_concise_log_omits_raw_transcript_by_default() {
  local project status

  project="$(make_project concise-log)"
  scenario 1 0 $'RAW TRANSCRIPT: .codex/skills/do-work/SKILL.md\nTASK DONE'
  scenario 2 0 $'RAW TRANSCRIPT: final plan dump\nALL TASKS DONE'

  run_loop "$project" --max-iterations 2
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "Verbose transcript logging: 0" || return 1
  assert_file_contains "$project/specode_loop.log" "do-work skill synced into project-local runner config." || return 1
  assert_file_contains "$project/specode_loop.log" "TASK DONE sentinel detected" || return 1
  assert_file_contains "$project/specode_loop.log" "ALL TASKS DONE sentinel detected" || return 1
  assert_file_not_contains "$project/specode_loop.log" "RAW TRANSCRIPT:" || return 1
  assert_file_not_contains "$project/specode_loop.log" ".codex/skills/do-work/SKILL.md" || return 1
}

test_verbose_log_includes_raw_transcript() {
  local project status

  project="$(make_project verbose-log)"
  scenario 1 0 $'RAW TRANSCRIPT: .codex/skills/do-work/SKILL.md\nALL TASKS DONE'

  SPECODE_LOOP_VERBOSE=1 run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "Verbose transcript logging: 1" || return 1
  assert_file_contains "$project/specode_loop.log" "RAW TRANSCRIPT: .codex/skills/do-work/SKILL.md" || return 1
  assert_file_contains "$project/specode_loop.log" "ALL TASKS DONE sentinel detected" || return 1
}

test_false_positive_sentinel_text_fails() {
  local project status

  project="$(make_project false-positive)"
  scenario 1 0 'The words TASK DONE are present, but not alone.'

  run_loop "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "FAILED, no exact success sentinel detected" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode_loop-false-positive-" || return 1
}

test_no_sentinel_failure_and_cleanup() {
  local project status

  project="$(make_project no-sentinel)"
  scenario 1 0 "ordinary output"

  run_loop "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "FAILED, no exact success sentinel detected" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode_loop-no-sentinel-" || return 1
}

test_interrupt_cleanup() {
  local project status

  project="$(make_project interrupt)"
  interrupt_scenario 1 "starting long run"

  run_loop "$project"
  status=$?

  assert_status 130 "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "Interrupted." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode_loop-interrupt-" || return 1
}

test_max_iteration_failure() {
  local project status

  project="$(make_project max-cap)"
  scenario 1 0 "TASK DONE"
  scenario 2 0 "TASK DONE"

  run_loop "$project" --max-iterations 2
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "reached max iterations (2) before ALL TASKS DONE" || return 1
  assert_equals "2" "$(wc -l <"$CURRENT_TEST_DIR/scenarios/rm.log" | tr -d ' ')" || return 1
}

test_direct_mode_and_prompt_contract() {
  local project status

  project="$(make_project prompt-contract)"
  scenario 1 0 "ALL TASKS DONE"

  run_loop "$project" --model test-model --effort high
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "run|specode_loop-prompt-contract-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "codex $project -- exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C $project -m test-model -c model_reasoning_effort=\"high\" -o $project/.specode_loop-last-message." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Use the project-local do-work skill for this task." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Do not modify .codex/skills/do-work as part of task work." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Do not make a git commit unless prd.md or plan.md explicitly requires it." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Select exactly first one undone Markdown checkbox task in plan.md for this run." || return 1
  assert_file_contains "$project/specode_loop.log" "Model: test-model" || return 1
  assert_file_contains "$project/specode_loop.log" "Reasoning effort: high" || return 1
}

run_case "missing documents and max validation" test_missing_documents_and_max_validation
run_case "full do-work skill copy and overwrite" test_skill_copy_and_overwrite
run_case "missing global skill fails before sandbox" test_missing_global_skill_fails_before_sandbox
run_case "dirty git warnings continue" test_dirty_git_warning
run_case "exact sentinels override nonzero sandbox status" test_exact_sentinels_and_nonzero_override
run_case "last-message sentinels are detected" test_last_message_sentinel_detection
run_case "concise logs omit raw transcript by default" test_concise_log_omits_raw_transcript_by_default
run_case "verbose logs include raw transcript" test_verbose_log_includes_raw_transcript
run_case "false-positive sentinel text fails" test_false_positive_sentinel_text_fails
run_case "no-sentinel output fails and cleans up" test_no_sentinel_failure_and_cleanup
run_case "interrupt cleans up active sandbox" test_interrupt_cleanup
run_case "max iterations fail before all tasks done" test_max_iteration_failure
run_case "direct-mode command and prompt contract" test_direct_mode_and_prompt_contract

printf '\n%s passed, %s failed\n' "$PASS_COUNT" "$FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
