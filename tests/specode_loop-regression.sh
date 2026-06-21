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

assert_file_missing_or_not_contains() {
  local file="$1"
  local needle="$2"

  if [[ -e "$file" ]]; then
    assert_file_not_contains "$file" "$needle"
  fi
}

assert_no_sandbox_failure_diagnostics() {
  local log_file="${1:-}"

  assert_file_not_contains "$CURRENT_TEST_DIR/stdout" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stderr" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stdout" "Last 30 captured output lines:" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stderr" "Last 30 captured output lines:" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stdout" "For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1." || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stderr" "For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1." || return 1

  if [[ -n "$log_file" ]]; then
    assert_file_missing_or_not_contains "$log_file" "Sandbox iteration failed without a success sentinel." || return 1
    assert_file_missing_or_not_contains "$log_file" "Last 30 captured output lines:" || return 1
    assert_file_missing_or_not_contains "$log_file" "For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1." || return 1
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

assert_temp_outputs_cleaned() {
  assert_no_paths_matching "$CURRENT_TEST_DIR/tmp/specode_loop.*" || return 1
}

make_test_dir() {
  CURRENT_TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/specode_loop-test.XXXXXX")"
  mkdir -p "$CURRENT_TEST_DIR/bin" "$CURRENT_TEST_DIR/codex-home/skills/do-work" "$CURRENT_TEST_DIR/scenarios" "$CURRENT_TEST_DIR/tmp"
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

    if [[ "${1:-}" == "codex" && -n "${2:-}" ]]; then
      skill_path="$2/.agents/skills/specode-do-work/SKILL.md"
      if [[ -f "$skill_path" ]]; then
        printf 'skill-before-run|%s|present\n' "$skill_path" >>"$FAKE_SBX_DIR/calls.log"
      else
        printf 'skill-before-run|%s|missing\n' "$skill_path" >>"$FAKE_SBX_DIR/calls.log"
      fi
    fi

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
    if [[ -f "$FAKE_SBX_DIR/rm.status" ]]; then
      exit "$(cat "$FAKE_SBX_DIR/rm.status")"
    fi
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

cleanup_failure() {
  local status="$1"

  printf '%s\n' "$status" >"$CURRENT_TEST_DIR/scenarios/rm.status"
}

run_loop() {
  local project="$1"
  shift

  run_loop_with_runner "$RUNNER" "$project" "$@"
}

run_loop_with_runner() {
  local runner="$1"
  local project="$2"
  shift 2

  (
    unset CODEX_HOME
    PATH="$CURRENT_TEST_DIR/bin:$PATH" \
      FAKE_SBX_DIR="$CURRENT_TEST_DIR/scenarios" \
      SPECODE_LOOP_VERBOSE="${SPECODE_LOOP_VERBOSE:-}" \
      TMPDIR="$CURRENT_TEST_DIR/tmp" \
      bash "$runner" "$project" "$@"
  ) >"$CURRENT_TEST_DIR/stdout" 2>"$CURRENT_TEST_DIR/stderr"
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
  assert_no_sandbox_failure_diagnostics "$project/specode_loop.log" || return 1
  assert_path_missing "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1

  project="$CURRENT_TEST_DIR/missing-plan"
  mkdir -p "$project"
  printf '# PRD\n' >"$project/prd.md"
  run_loop "$project"
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "required plan file is missing" || return 1
  assert_no_sandbox_failure_diagnostics "$project/specode_loop.log" || return 1
  assert_path_missing "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1

  project="$(make_project invalid-max)"
  run_loop "$project" --max-iterations 0
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "--max-iterations must be a positive integer" || return 1
  assert_no_sandbox_failure_diagnostics "$project/specode_loop.log" || return 1
  assert_path_missing "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1

  project="$(make_project invalid-effort)"
  run_loop "$project" --effort enormous
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "--effort must be one of: minimal, low, medium, high, xhigh" || return 1
  assert_no_sandbox_failure_diagnostics "$project/specode_loop.log" || return 1
  assert_path_missing "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1

  project="$(make_project unknown-arg)"
  run_loop "$project" --unexpected-option
  status=$?
  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "unknown argument: --unexpected-option" || return 1
  assert_no_sandbox_failure_diagnostics "$project/specode_loop.log" || return 1
  assert_path_missing "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1
}

test_skill_copy_and_overwrite() {
  local project status copied_skill copied_reference unrelated_skill unrelated_agent_config

  project="$(make_project skill-copy)"
  copied_skill="$project/.agents/skills/specode-do-work/SKILL.md"
  copied_reference="$project/.agents/skills/specode-do-work/references/workflow.txt"
  unrelated_skill="$project/.agents/skills/project-owned/SKILL.md"
  unrelated_agent_config="$project/.agents/README.md"
  mkdir -p "$project/.agents/skills/specode-do-work"
  printf 'stale local skill\n' >"$copied_skill"
  mkdir -p "$project/.agents/skills/specode-do-work/stale-dir"
  printf 'stale nested asset\n' >"$project/.agents/skills/specode-do-work/stale-dir/old.txt"
  mkdir -p "$project/.agents/skills/project-owned"
  printf 'project-owned skill\n' >"$unrelated_skill"
  printf 'project-owned agent config\n' >"$unrelated_agent_config"

  scenario 1 0 "ALL TASKS DONE"
  run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$copied_skill" "name: specode-do-work" || return 1
  assert_file_not_contains "$copied_skill" "stale local skill" || return 1
  assert_file_contains "$copied_reference" "Specode Loop runner workflow" || return 1
  assert_path_missing "$project/.agents/skills/specode-do-work/stale-dir/old.txt" || return 1
  assert_file_contains "$unrelated_skill" "project-owned skill" || return 1
  assert_file_contains "$unrelated_agent_config" "project-owned agent config" || return 1
  assert_path_exists "$project/.agents/skills/specode-do-work" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "skill-before-run|$copied_skill|present" || return 1
}

test_missing_global_skill_is_not_required() {
  local project status

  project="$(make_project missing-skill)"
  rm -rf "$CURRENT_TEST_DIR/codex-home/skills/do-work"
  scenario 1 0 "ALL TASKS DONE"

  run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  assert_path_exists "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1
  assert_file_contains "$project/specode_loop.log" "Bundled workflow skill synced: specode-do-work:$project/.agents/skills/specode-do-work" || return 1
}

test_codex_home_is_unset_for_normal_runs() {
  local project status

  project="$(make_project unset-codex-home)"
  scenario 1 0 "ALL TASKS DONE"

  run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  assert_path_exists "$CURRENT_TEST_DIR/scenarios/calls.log" || return 1
  assert_file_contains "$project/specode_loop.log" "Bundled workflow skill synced: specode-do-work:$project/.agents/skills/specode-do-work" || return 1
}

test_runner_has_no_codex_home_skill_resolution() {
  if grep -Eq 'CODEX_HOME|global_do_work_skill_path' "$RUNNER"; then
    printf 'runner still references hidden user skill state\n' >&2
    grep -En 'CODEX_HOME|global_do_work_skill_path' "$RUNNER" >&2 || true
    return 1
  fi
}

test_missing_bundled_skill_fails_before_sandbox() {
  local project status isolated_runner

  project="$(make_project missing-bundled-source)"
  isolated_runner="$CURRENT_TEST_DIR/isolated-runner/scripts/specode_loop.sh"
  mkdir -p "$(dirname "$isolated_runner")"
  cp "$RUNNER" "$isolated_runner" || return 1

  run_loop_with_runner "$isolated_runner" "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "bundled workflow skill directory is missing" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "isolated-runner/.agents/skills/specode-do-work" || return 1
  assert_no_sandbox_failure_diagnostics "$project/specode_loop.log" || return 1
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
  assert_file_contains "$project/specode_loop.log" "Sandbox cleanup: removed sandbox specode-loop-sentinel-flow-" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stdout" "Sandbox cleanup:" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode-loop-sentinel-flow-" || return 1
  assert_equals "2" "$(wc -l <"$CURRENT_TEST_DIR/scenarios/rm.log" | tr -d ' ')" || return 1
  assert_temp_outputs_cleaned || return 1
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
  assert_file_contains "$project/specode_loop.log" "Bundled workflow skill synced: specode-do-work:$project/.agents/skills/specode-do-work" || return 1
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
  assert_temp_outputs_cleaned || return 1
}

test_verbose_no_sentinel_failure_keeps_raw_transcript_and_summary() {
  local project status output_lines line

  project="$(make_project verbose-failure)"
  output_lines=""
  for line in $(seq 1 35); do
    output_lines="${output_lines}verbose failure line $(printf '%02d' "$line")"$'\n'
  done
  scenario 1 7 "${output_lines%$'\n'}"

  SPECODE_LOOP_VERBOSE=1 run_loop "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "Verbose transcript logging: 1" || return 1
  assert_file_contains "$project/specode_loop.log" "verbose failure line 01" || return 1
  assert_file_contains "$project/specode_loop.log" "verbose failure line 05" || return 1
  assert_file_contains "$project/specode_loop.log" "verbose failure line 35" || return 1
  assert_file_contains "$project/specode_loop.log" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_contains "$project/specode_loop.log" "Last 30 captured output lines:" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox cleanup: removed sandbox specode-loop-verbose-failure-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode-loop-verbose-failure-" || return 1
  assert_temp_outputs_cleaned || return 1
}

test_false_positive_sentinel_text_fails() {
  local project status

  project="$(make_project false-positive)"
  scenario 1 0 'The words TASK DONE are present, but not alone.'

  run_loop "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "FAILED, no exact success sentinel detected" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode-loop-false-positive-" || return 1
}

test_no_sentinel_failure_and_cleanup() {
  local project status output_lines line

  project="$(make_project no-sentinel)"
  output_lines=""
  for line in $(seq 1 35); do
    output_lines="${output_lines}agent output line $(printf '%02d' "$line")"$'\n'
  done
  scenario 1 7 "${output_lines%$'\n'}"

  run_loop "$project"
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$project/specode_loop.log" "FAILED, no exact success sentinel detected" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Iteration: 1/10" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox: specode-loop-no-sentinel-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox command exit code: 7" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Expected success sentinels:" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "- TASK DONE" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "- ALL TASKS DONE" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Project log: $project/specode_loop.log" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Last 30 captured output lines:" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "agent output line 06" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "agent output line 35" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1." || return 1
  assert_file_contains "$project/specode_loop.log" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_contains "$project/specode_loop.log" "Iteration: 1/10" || return 1
  assert_file_contains "$project/specode_loop.log" "Sandbox command exit code: 7" || return 1
  assert_file_contains "$project/specode_loop.log" "Project log: $project/specode_loop.log" || return 1
  assert_file_contains "$project/specode_loop.log" "Last 30 captured output lines:" || return 1
  assert_file_contains "$project/specode_loop.log" "agent output line 06" || return 1
  assert_file_contains "$project/specode_loop.log" "agent output line 35" || return 1
  assert_file_not_contains "$project/specode_loop.log" "agent output line 05" || return 1
  assert_file_not_contains "$project/specode_loop.log" "agent output line 01" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox cleanup: removed sandbox specode-loop-no-sentinel-" || return 1
  assert_file_contains "$project/specode_loop.log" "Sandbox cleanup: removed sandbox specode-loop-no-sentinel-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode-loop-no-sentinel-" || return 1
  assert_temp_outputs_cleaned || return 1
}

test_failed_cleanup_preserves_iteration_failure() {
  local project status

  project="$(make_project failed-cleanup)"
  scenario 1 7 "ordinary output without a sentinel"
  cleanup_failure 23

  run_loop "$project"
  status=$?

  assert_status 1 "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox command exit code: 7" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox cleanup: failed to remove sandbox specode-loop-failed-cleanup-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "(exit code: 23)" || return 1
  assert_file_contains "$project/specode_loop.log" "Sandbox cleanup: failed to remove sandbox specode-loop-failed-cleanup-" || return 1
  assert_file_contains "$project/specode_loop.log" "(exit code: 23)" || return 1
  assert_temp_outputs_cleaned || return 1
}

test_interrupt_cleanup() {
  local project status

  project="$(make_project interrupt)"
  interrupt_scenario 1 "starting long run"

  run_loop "$project"
  status=$?

  assert_status 130 "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stderr" "Interrupted." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Sandbox cleanup: removed sandbox specode-loop-interrupt-" || return 1
  assert_file_contains "$project/specode_loop.log" "Sandbox cleanup: removed sandbox specode-loop-interrupt-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/rm.log" "rm|specode-loop-interrupt-" || return 1
  assert_temp_outputs_cleaned || return 1
}

test_max_iteration_failure() {
  local project status

  project="$(make_project max-cap)"
  scenario 1 0 "TASK DONE"
  scenario 2 0 "TASK DONE"

  run_loop "$project" --max-iterations 2
  status=$?

  assert_failure "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Specode Loop stopped at the maximum iteration cap." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Configured maximum iterations reached: 2" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "ALL TASKS DONE was not observed." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/stdout" "Project log: $project/specode_loop.log" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stdout" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/stdout" "Last 30 captured output lines:" || return 1
  assert_file_contains "$project/specode_loop.log" "reached max iterations (2) before ALL TASKS DONE" || return 1
  assert_file_contains "$project/specode_loop.log" "Specode Loop stopped at the maximum iteration cap." || return 1
  assert_file_contains "$project/specode_loop.log" "Configured maximum iterations reached: 2" || return 1
  assert_file_contains "$project/specode_loop.log" "ALL TASKS DONE was not observed." || return 1
  assert_file_contains "$project/specode_loop.log" "Project log: $project/specode_loop.log" || return 1
  assert_file_not_contains "$project/specode_loop.log" "Sandbox iteration failed without a success sentinel." || return 1
  assert_file_not_contains "$project/specode_loop.log" "Last 30 captured output lines:" || return 1
  assert_equals "2" "$(wc -l <"$CURRENT_TEST_DIR/scenarios/rm.log" | tr -d ' ')" || return 1
  assert_temp_outputs_cleaned || return 1
}

test_direct_mode_and_prompt_contract() {
  local project status

  project="$(make_project prompt-contract)"
  scenario 1 0 "ALL TASKS DONE"

  run_loop "$project" --model test-model --effort high
  status=$?

  assert_success "$status" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "run|specode-loop-prompt-contract-" || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "codex $project -- exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C $project -m test-model -c model_reasoning_effort=\"high\" -o $project/.specode_loop-last-message." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Use the project-local specode-do-work skill." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Work on AFK Phases only. Do not work on HITL Phases." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Select exactly one undone AFK Phase in plan.md for this run." || return 1
  assert_file_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "If no undone AFK Phases remain, output exactly:" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "runner-managed configuration copied in by Specode Loop" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Do not modify .agents/skills/specode-do-work as part of task work." || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "project-local do-work skill" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/scenarios/calls.log" ".codex/skills/do-work" || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Do not make a git commit unless prd.md or plan.md explicitly requires it." || return 1
  assert_file_not_contains "$CURRENT_TEST_DIR/scenarios/calls.log" "Work directly in the project working tree" || return 1
  assert_file_contains "$project/specode_loop.log" "Model: test-model" || return 1
  assert_file_contains "$project/specode_loop.log" "Reasoning effort: high" || return 1
}

test_sandbox_names_are_hostname_safe() {
  local project status sandbox_name

  project="$(make_project fixture_name_with_underscores_and_extra_segments_abcdefghijklmnopqrstuvwxyz)"
  scenario 1 0 "ALL TASKS DONE"

  run_loop "$project"
  status=$?

  assert_success "$status" || return 1
  sandbox_name="$(sed -n 's/^run|\([^|]*\)|.*/\1/p' "$CURRENT_TEST_DIR/scenarios/calls.log" | head -n 1)"
  [[ -n "$sandbox_name" ]] || {
    printf 'expected fake sbx call to include sandbox name\n' >&2
    return 1
  }
  if [[ "${#sandbox_name}" -gt 63 ]]; then
    printf 'expected sandbox name length <= 63, got %s: %s\n' "${#sandbox_name}" "$sandbox_name" >&2
    return 1
  fi
  if [[ ! "$sandbox_name" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
    printf 'expected hostname-safe sandbox name, got: %s\n' "$sandbox_name" >&2
    return 1
  fi
}

run_case "missing documents and max validation" test_missing_documents_and_max_validation
run_case "full do-work skill copy and overwrite" test_skill_copy_and_overwrite
run_case "missing global skill is not required" test_missing_global_skill_is_not_required
run_case "normal runs work with CODEX_HOME unset" test_codex_home_is_unset_for_normal_runs
run_case "runner does not resolve CODEX_HOME skills" test_runner_has_no_codex_home_skill_resolution
run_case "missing bundled skill fails before sandbox" test_missing_bundled_skill_fails_before_sandbox
run_case "dirty git warnings continue" test_dirty_git_warning
run_case "exact sentinels override nonzero sandbox status" test_exact_sentinels_and_nonzero_override
run_case "last-message sentinels are detected" test_last_message_sentinel_detection
run_case "concise logs omit raw transcript by default" test_concise_log_omits_raw_transcript_by_default
run_case "verbose logs include raw transcript" test_verbose_log_includes_raw_transcript
run_case "verbose no-sentinel failure keeps raw transcript and summary" test_verbose_no_sentinel_failure_keeps_raw_transcript_and_summary
run_case "false-positive sentinel text fails" test_false_positive_sentinel_text_fails
run_case "no-sentinel output fails and cleans up" test_no_sentinel_failure_and_cleanup
run_case "failed cleanup preserves original iteration failure" test_failed_cleanup_preserves_iteration_failure
run_case "interrupt cleans up active sandbox" test_interrupt_cleanup
run_case "max iterations fail before all tasks done" test_max_iteration_failure
run_case "direct-mode command and prompt contract" test_direct_mode_and_prompt_contract
run_case "sandbox names stay hostname-safe" test_sandbox_names_are_hostname_safe

printf '\n%s passed, %s failed\n' "$PASS_COUNT" "$FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
