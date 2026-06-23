import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RUNNER = ROOT_DIR / "scripts" / "specode_loop.py"
SPECODE_SKILL = ROOT_DIR / ".agents" / "skills" / "specode-do-work"


def run_loop(
    project: Path | None = None,
    *args: str,
    path: str | None = None,
    runner: Path = RUNNER,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(runner)]
    if project is not None:
        command.append(str(project))
    command.extend(args)
    env = os.environ.copy()
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def prepare_fake_runtime(tmp_path: Path, monkeypatch) -> tuple[str, Path, Path]:
    path, calls_log = install_fake_sbx(tmp_path)
    rm_log = tmp_path / "sbx-rm.log"
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    monkeypatch.setenv("FAKE_SBX_RM_CALLS", str(rm_log))
    monkeypatch.setenv("FAKE_SBX_DIR", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return path, calls_log, rm_log


def make_project(tmp_path: Path, name: str = "project") -> Path:
    project = tmp_path / name
    project.mkdir()
    (project / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (project / "plan.md").write_text("# Plan\n\n- [ ] Do one task\n", encoding="utf-8")
    return project


def install_fake_sbx(tmp_path: Path) -> tuple[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_log = tmp_path / "sbx-calls.log"
    fake_sbx = bin_dir / "sbx"
    fake_sbx.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        "cmd=\"${1:-}\"\n"
        "shift || true\n"
        "case \"$cmd\" in\n"
        "  run)\n"
        "    name=\"\"\n"
        "    if [[ \"${1:-}\" == \"--name\" ]]; then\n"
        "      name=\"${2:-}\"\n"
        "      shift 2\n"
        "    fi\n"
        "    count_file=\"$FAKE_SBX_DIR/count\"\n"
        "    count=0\n"
        "    if [[ -f \"$count_file\" ]]; then count=\"$(cat \"$count_file\")\"; fi\n"
        "    count=$((count + 1))\n"
        "    printf '%s\\n' \"$count\" >\"$count_file\"\n"
        "    printf 'run|%s|%s\\n' \"$name\" \"$*\" >>\"$FAKE_SBX_CALLS\"\n"
        "    if [[ \"${1:-}\" == \"codex\" && -n \"${2:-}\" ]]; then\n"
        "      skill_path=\"$2/.agents/skills/specode-do-work/SKILL.md\"\n"
        "      if [[ -f \"$skill_path\" ]]; then\n"
        "        printf 'skill-before-run|%s|present\\n' \"$skill_path\" >>\"$FAKE_SBX_CALLS\"\n"
        "      else\n"
        "        printf 'skill-before-run|%s|missing\\n' \"$skill_path\" >>\"$FAKE_SBX_CALLS\"\n"
        "      fi\n"
        "    fi\n"
        "    output_file=\"$FAKE_SBX_DIR/run_${count}.out\"\n"
        "    status_file=\"$FAKE_SBX_DIR/run_${count}.status\"\n"
        "    interrupt_file=\"$FAKE_SBX_DIR/run_${count}.interrupt\"\n"
        "    last_message_file=\"$FAKE_SBX_DIR/run_${count}.last\"\n"
        "    if [[ -f \"$output_file\" ]]; then cat \"$output_file\"; fi\n"
        "    if [[ -f \"$last_message_file\" ]]; then\n"
        "      output_path=\"\"\n"
        "      previous=\"\"\n"
        "      for arg in \"$@\"; do\n"
        "        if [[ \"$previous\" == \"-o\" ]]; then output_path=\"$arg\"; break; fi\n"
        "        previous=\"$arg\"\n"
        "      done\n"
        "      if [[ -n \"$output_path\" ]]; then cat \"$last_message_file\" >\"$output_path\"; fi\n"
        "    fi\n"
        "    if [[ -f \"$interrupt_file\" ]]; then\n"
        "      kill -TERM \"$PPID\"\n"
        "      sleep 0.1\n"
        "      exit 143\n"
        "    fi\n"
        "    if [[ -f \"$status_file\" ]]; then exit \"$(cat \"$status_file\")\"; fi\n"
        "    exit 0\n"
        "    ;;\n"
        "  rm)\n"
        "    printf 'rm|%s\\n' \"${1:-}\" >>\"$FAKE_SBX_RM_CALLS\"\n"
        "    if [[ -f \"$FAKE_SBX_DIR/rm.status\" ]]; then exit \"$(cat \"$FAKE_SBX_DIR/rm.status\")\"; fi\n"
        "    exit 0\n"
        "    ;;\n"
        "  *)\n"
        "    printf 'unexpected fake sbx command: %s\\n' \"$cmd\" >&2\n"
        "    exit 127\n"
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_sbx.chmod(0o755)
    path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return path, calls_log


def write_scenario(tmp_path: Path, run_number: int, output: str, status: int = 0) -> None:
    (tmp_path / f"run_{run_number}.out").write_text(output, encoding="utf-8")
    (tmp_path / f"run_{run_number}.status").write_text(f"{status}\n", encoding="utf-8")


def write_last_message(tmp_path: Path, run_number: int, output: str) -> None:
    (tmp_path / f"run_{run_number}.last").write_text(output, encoding="utf-8")


def write_interrupt(tmp_path: Path, run_number: int, output: str) -> None:
    (tmp_path / f"run_{run_number}.out").write_text(output, encoding="utf-8")
    (tmp_path / f"run_{run_number}.interrupt").write_text("interrupt\n", encoding="utf-8")


def write_cleanup_status(tmp_path: Path, status: int) -> None:
    (tmp_path / "rm.status").write_text(f"{status}\n", encoding="utf-8")


def assert_sandbox_not_called(calls_log: Path) -> None:
    assert not calls_log.exists(), calls_log.read_text(encoding="utf-8") if calls_log.exists() else ""


def assert_bundled_skill_not_synced(project: Path) -> None:
    assert not (project / ".agents" / "skills" / "specode-do-work").exists()


def assert_sandbox_called(calls_log: Path) -> str:
    assert calls_log.exists()
    return calls_log.read_text(encoding="utf-8")


def assert_no_temp_artifacts(tmp_path: Path, project: Path) -> None:
    assert not list(tmp_path.glob("specode_loop.*"))
    assert not list(project.glob(".specode_loop-last-message.*"))


def re_fullmatch_hostname(value: str) -> re.Match[str] | None:
    return re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", value)


def test_help_describes_python_command_contract() -> None:
    result = run_loop(None, "--help")

    assert result.returncode == 0
    assert "Usage: scripts/specode_loop.py PROJECT_DIR [options]" in result.stdout
    assert "--prd PATH" in result.stdout
    assert "--plan PATH" in result.stdout
    assert "--max-iterations N" in result.stdout
    assert "--reasoning-effort EFFORT" in result.stdout
    assert result.stderr == ""


def test_blessed_uv_run_python_invocation_shows_help() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "scripts/specode_loop.py", "--help"],
        cwd=ROOT_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage: scripts/specode_loop.py PROJECT_DIR [options]" in result.stdout


def test_missing_target_project_argument_prints_usage() -> None:
    result = run_loop()

    assert result.returncode == 2
    assert "Usage: scripts/specode_loop.py PROJECT_DIR [options]" in result.stderr
    assert result.stdout == ""


def test_option_parsing_and_valid_run_execute_sandbox(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(
        project,
        "--max-iterations",
        "7",
        "--model",
        "test-model",
        "--reasoning-effort",
        "medium",
        path=path,
    )

    assert result.returncode == 0
    assert "Specode Loop preflight passed." in result.stdout
    assert f"Project: {project}" in result.stdout
    assert f"PRD document: {project / 'prd.md'}" in result.stdout
    assert f"Plan document: {project / 'plan.md'}" in result.stdout
    assert "Max iterations: 7" in result.stdout
    assert "Model: test-model" in result.stdout
    assert "Reasoning effort: medium" in result.stdout
    calls = assert_sandbox_called(calls_log)
    assert "run|specode-loop-project-" in calls
    assert f"codex {project} -- exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C {project}" in calls
    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert f"PRD document: {project / 'prd.md'}" in log
    assert f"Plan document: {project / 'plan.md'}" in log
    assert "ALL TASKS DONE sentinel detected" in log
    assert "rm|specode-loop-project-" in rm_log.read_text(encoding="utf-8")
    assert_no_temp_artifacts(tmp_path, project)


def test_custom_planning_document_paths_resolve_from_project_and_reach_prompt(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "custom-docs"
    project.mkdir()
    prd = project / "planning" / "requirements"
    plan = project / "work" / "phases.todo"
    prd.parent.mkdir()
    plan.parent.mkdir()
    prd.write_text("# Custom PRD\n", encoding="utf-8")
    plan.write_text("# Custom Plan\n\n- [ ] Do one task\n", encoding="utf-8")
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(
        project,
        "--prd",
        "planning/requirements",
        "--plan",
        "work/phases.todo",
        path=path,
    )

    assert result.returncode == 0
    assert f"PRD document: {prd}" in result.stdout
    assert f"Plan document: {plan}" in result.stdout
    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert f"PRD document: {prd}" in log
    assert f"Plan document: {plan}" in log
    calls = assert_sandbox_called(calls_log)
    assert "PRD document: planning/requirements" in calls
    assert "Plan document: work/phases.todo" in calls


def test_absolute_custom_planning_document_paths_inside_project_are_accepted(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "absolute-docs"
    project.mkdir()
    prd = project / "docs" / "product brief"
    plan = project / "plans" / "release"
    prd.parent.mkdir()
    plan.parent.mkdir()
    prd.write_text("# PRD\n", encoding="utf-8")
    plan.write_text("# Plan\n\n- [ ] Do one task\n", encoding="utf-8")
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, "--prd", str(prd), "--plan", str(plan), path=path)

    assert result.returncode == 0
    assert f"PRD document: {prd}" in result.stdout
    assert f"Plan document: {plan}" in result.stdout
    calls = assert_sandbox_called(calls_log)
    assert "PRD document: docs/product brief" in calls
    assert "Plan document: plans/release" in calls


def test_successive_task_done_iterations_continue_until_all_tasks_done(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "multi-step")
    path, calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "working\nTASK DONE\n")
    write_scenario(tmp_path, 2, "finishing\nALL TASKS DONE\n")

    result = run_loop(project, "--max-iterations", "3", path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    calls = assert_sandbox_called(calls_log)
    assert result.returncode == 0
    assert "working" in result.stdout
    assert "finishing" in result.stdout
    assert "TASK DONE sentinel detected; iteration successful" in log
    assert "ALL TASKS DONE sentinel detected; overall run complete" in log
    assert calls.count("run|specode-loop-multi-step-") == 2
    assert rm_log.read_text(encoding="utf-8").count("rm|specode-loop-multi-step-") == 2
    assert_no_temp_artifacts(tmp_path, project)


def test_exact_sentinel_lines_are_required_and_false_positive_text_fails(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "false-positive")
    path, _calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "The words TASK DONE are present, but not alone.\n")

    result = run_loop(project, path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "FAILED, no exact success sentinel detected" in log
    assert "TASK DONE sentinel detected" not in log
    assert "Sandbox cleanup: removed sandbox specode-loop-false-positive-" in result.stdout
    assert "rm|specode-loop-false-positive-" in rm_log.read_text(encoding="utf-8")


def test_no_sentinel_failure_prints_summary_and_cleans_up(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "no-sentinel")
    path, _calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    output = "".join(f"agent output line {line:02d}\n" for line in range(1, 36))
    write_scenario(tmp_path, 1, output, status=7)

    result = run_loop(project, path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "FAILED, no exact success sentinel detected" in log
    assert "Sandbox iteration failed without a success sentinel." in result.stdout
    assert "Iteration: 1/10" in result.stdout
    assert "Sandbox: specode-loop-no-sentinel-" in result.stdout
    assert "Sandbox command exit code: 7" in result.stdout
    assert "Expected success sentinels:" in result.stdout
    assert "- TASK DONE" in result.stdout
    assert "- ALL TASKS DONE" in result.stdout
    assert f"Project log: {project / 'specode_loop.log'}" in result.stdout
    assert "Last 30 captured output lines:" in result.stdout
    assert "agent output line 06" in result.stdout
    assert "agent output line 35" in result.stdout
    assert "For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1." in result.stdout
    assert "Sandbox iteration failed without a success sentinel." in log
    assert "agent output line 06" in log
    assert "agent output line 35" in log
    assert "agent output line 05" not in log
    assert "Sandbox cleanup: removed sandbox specode-loop-no-sentinel-" in result.stdout
    assert "rm|specode-loop-no-sentinel-" in rm_log.read_text(encoding="utf-8")
    assert_no_temp_artifacts(tmp_path, project)


def test_failed_cleanup_preserves_iteration_failure_status(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "failed-cleanup")
    path, _calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ordinary output without a sentinel\n", status=7)
    write_cleanup_status(tmp_path, 23)

    result = run_loop(project, path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "Sandbox iteration failed without a success sentinel." in result.stdout
    assert "Sandbox command exit code: 7" in result.stdout
    assert "Sandbox cleanup: failed to remove sandbox specode-loop-failed-cleanup-" in result.stdout
    assert "(exit code: 23)" in result.stdout
    assert "Sandbox cleanup: failed to remove sandbox specode-loop-failed-cleanup-" in log
    assert "(exit code: 23)" in log
    assert_no_temp_artifacts(tmp_path, project)


def test_interrupt_cleans_temp_files_and_active_sandbox(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "interrupt")
    path, _calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_interrupt(tmp_path, 1, "starting long run\n")

    result = run_loop(project, path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 130
    assert "Interrupted." in result.stderr
    assert "Sandbox cleanup: removed sandbox specode-loop-interrupt-" in result.stdout
    assert "Sandbox cleanup: removed sandbox specode-loop-interrupt-" in log
    assert "rm|specode-loop-interrupt-" in rm_log.read_text(encoding="utf-8")
    assert_no_temp_artifacts(tmp_path, project)


def test_max_iteration_cap_fails_without_no_sentinel_diagnostics(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "max-cap")
    path, _calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "TASK DONE\n")
    write_scenario(tmp_path, 2, "TASK DONE\n")

    result = run_loop(project, "--max-iterations", "2", path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "Specode Loop stopped at the maximum iteration cap." in result.stdout
    assert "Configured maximum iterations reached: 2" in result.stdout
    assert "Stop reason: reached max iterations (2) before ALL TASKS DONE." in result.stdout
    assert "ALL TASKS DONE was not observed." in result.stdout
    assert f"Project log: {project / 'specode_loop.log'}" in result.stdout
    assert "Sandbox iteration failed without a success sentinel." not in result.stdout
    assert "Last 30 captured output lines:" not in result.stdout
    assert "Specode Loop stopped at the maximum iteration cap." in log
    assert "Configured maximum iterations reached: 2" in log
    assert "reached max iterations (2) before ALL TASKS DONE" in log
    assert "Sandbox iteration failed without a success sentinel." not in log
    assert "Last 30 captured output lines:" not in log
    assert rm_log.read_text(encoding="utf-8").count("rm|specode-loop-max-cap-") == 2
    assert_no_temp_artifacts(tmp_path, project)


def test_sentinel_detected_from_final_message_file(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "final-message")
    path, _calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "streamed output without a sentinel\n")
    write_last_message(tmp_path, 1, "TASK DONE\n")
    write_scenario(tmp_path, 2, "second streamed output without a sentinel\n")
    write_last_message(tmp_path, 2, "ALL TASKS DONE\n")

    result = run_loop(project, "--max-iterations", "2", path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "Captured Codex final message from --output-last-message." in log
    assert "TASK DONE sentinel detected; iteration successful" in log
    assert "ALL TASKS DONE sentinel detected; overall run complete" in log
    assert_no_temp_artifacts(tmp_path, project)


def test_success_sentinel_overrides_nonzero_sandbox_exit(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "nonzero-sentinel")
    path, calls_log, rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "TASK DONE\n", status=42)
    write_scenario(tmp_path, 2, "ALL TASKS DONE\n", status=42)

    result = run_loop(project, "--max-iterations", "2", path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "TASK DONE sentinel detected; iteration successful (command exit code: 42)" in log
    assert "ALL TASKS DONE sentinel detected; overall run complete (command exit code: 42)" in log
    assert assert_sandbox_called(calls_log).count("run|specode-loop-nonzero-sentinel-") == 2
    assert rm_log.read_text(encoding="utf-8").count("rm|specode-loop-nonzero-sentinel-") == 2


def test_default_log_is_concise_and_omits_raw_transcript(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "concise-log")
    path, _calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "RAW TRANSCRIPT: internal work details\nTASK DONE\n")
    write_scenario(tmp_path, 2, "RAW TRANSCRIPT: final plan dump\nALL TASKS DONE\n")
    write_last_message(tmp_path, 2, "RAW FINAL MESSAGE: plan summary\nALL TASKS DONE\n")

    result = run_loop(project, "--max-iterations", "2", path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "Specode Loop preflight passed." in log
    assert "Bundled workflow skill synced: specode-do-work:" in log
    assert "Verbose transcript logging: 0" in log
    assert "Starting non-interactive Codex run in Docker Sandbox direct workspace mode." in log
    assert "Captured Codex final message from --output-last-message." in log
    assert "TASK DONE sentinel detected" in log
    assert "ALL TASKS DONE sentinel detected" in log
    assert "Sandbox cleanup: removed sandbox specode-loop-concise-log-" in log
    assert "RAW TRANSCRIPT:" not in log
    assert "RAW FINAL MESSAGE:" not in log


def test_verbose_log_includes_raw_transcript_and_final_message(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "verbose-log")
    path, _calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("SPECODE_LOOP_VERBOSE", "1")
    write_scenario(tmp_path, 1, "RAW TRANSCRIPT: detailed sandbox output\n")
    write_last_message(tmp_path, 1, "RAW FINAL MESSAGE: detailed final note\nALL TASKS DONE\n")

    result = run_loop(project, path=path)

    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "Verbose transcript logging: 1" in log
    assert "RAW TRANSCRIPT: detailed sandbox output" in log
    assert "===== Codex final message captured from --output-last-message =====" in log
    assert "RAW FINAL MESSAGE: detailed final note" in log
    assert "ALL TASKS DONE sentinel detected" in log
    assert_no_temp_artifacts(tmp_path, project)


def test_prompt_and_codex_argument_order_match_python_command_contract(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "prompt-contract")
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, "--model", "test-model", "--effort", "high", path=path)

    calls = assert_sandbox_called(calls_log)
    assert result.returncode == 0
    assert (
        f"codex {project} -- exec --dangerously-bypass-approvals-and-sandbox "
        f"--skip-git-repo-check -C {project} -m test-model -c "
        f"model_reasoning_effort=\"high\" -o {project}/.specode_loop-last-message."
    ) in calls
    assert "Use the project-local specode-do-work skill." in calls
    assert "PRD document: prd.md" in calls
    assert "Plan document: plan.md" in calls
    assert "Read the PRD document and plan document before choosing work." in calls
    assert "Work on AFK Phases only. Do not work on HITL Phases." in calls
    assert "Select exactly one undone AFK Phase in the plan document for this run." in calls
    assert "Mark the completed AFK Phase done in the plan document by changing its checkbox from \"[ ]\" to \"[x]\"." in calls
    assert "If no undone AFK Phases remain, output exactly:" in calls
    assert "When the selected AFK Phase is complete and the plan document has been updated, output exactly:" in calls


def test_sandbox_names_are_hostname_safe_and_length_bounded(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "fixture_name_with_underscores_and_extra_segments_abcdefghijklmnopqrstuvwxyz")
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, path=path)

    calls = assert_sandbox_called(calls_log)
    sandbox_name = calls.split("|", 2)[1]
    assert result.returncode == 0
    assert len(sandbox_name) <= 63
    assert re_fullmatch_hostname(sandbox_name)


def test_bundled_skill_is_copied_and_owned_target_is_overwritten(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")
    copied_skill = project / ".agents" / "skills" / "specode-do-work" / "SKILL.md"
    copied_reference = project / ".agents" / "skills" / "specode-do-work" / "references" / "workflow.txt"
    stale_file = project / ".agents" / "skills" / "specode-do-work" / "stale-dir" / "old.txt"
    unrelated_skill = project / ".agents" / "skills" / "project-owned" / "SKILL.md"
    unrelated_agent_config = project / ".agents" / "README.md"

    copied_skill.parent.mkdir(parents=True)
    copied_skill.write_text("stale local skill\n", encoding="utf-8")
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale nested asset\n", encoding="utf-8")
    unrelated_skill.parent.mkdir(parents=True)
    unrelated_skill.write_text("project-owned skill\n", encoding="utf-8")
    unrelated_agent_config.write_text("project-owned agent config\n", encoding="utf-8")

    result = run_loop(project, path=path)

    assert result.returncode == 0
    assert "Bundled workflow skill synced: specode-do-work:" in result.stdout
    copied_skill_text = copied_skill.read_text(encoding="utf-8")
    assert "name: specode-do-work" in copied_skill_text
    assert "Read the PRD document and plan document named by the runner prompt." in copied_skill_text
    assert "Follow the runner prompt's task-selection rules exactly" in copied_skill_text
    assert "first undone Markdown checkbox task" not in copied_skill_text
    assert "Read `prd.md` and `plan.md` in the project root." not in copied_skill_text
    assert "Do not make a git commit unless `prd.md` or `plan.md` explicitly requires it." not in copied_skill_text
    assert "stale local skill" not in copied_skill_text
    assert "Specode Loop runner workflow" in copied_reference.read_text(encoding="utf-8")
    assert not stale_file.exists()
    assert unrelated_skill.read_text(encoding="utf-8") == "project-owned skill\n"
    assert unrelated_agent_config.read_text(encoding="utf-8") == "project-owned agent config\n"
    assert f"skill-before-run|{copied_skill}|present" in assert_sandbox_called(calls_log)


def test_missing_bundled_skill_source_fails_before_sandbox_execution(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    isolated_runner = tmp_path / "isolated-runner" / "scripts" / "specode_loop.py"
    isolated_runner.parent.mkdir(parents=True)
    shutil.copyfile(RUNNER, isolated_runner)

    result = run_loop(project, path=path, runner=isolated_runner)

    assert result.returncode == 1
    assert "Error: bundled workflow skill directory is missing:" in result.stderr
    assert "isolated-runner/.agents/skills/specode-do-work" in result.stderr
    assert "Specode Loop preflight passed." not in result.stdout
    assert_sandbox_not_called(calls_log)


def test_dirty_git_state_warns_and_continues(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=project, check=True)
    subprocess.run(["git", "add", "prd.md", "plan.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=project, check=True)
    (project / "prd.md").write_text("# PRD\n\nchanged\n", encoding="utf-8")
    (project / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=project, check=True)

    result = run_loop(project, path=path)

    assert result.returncode == 0
    assert f"Warning: {project} has existing unstaged changes. Continuing." in result.stderr
    assert f"Warning: {project} has existing staged changes. Continuing." in result.stderr
    assert "Specode Loop preflight passed." in result.stdout
    assert_sandbox_called(calls_log)


def test_hidden_user_skill_state_is_not_consulted(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex-home"))

    result = run_loop(project, path=path)

    copied_skill = project / ".agents" / "skills" / "specode-do-work" / "SKILL.md"
    assert result.returncode == 0
    assert copied_skill.read_text(encoding="utf-8") == (SPECODE_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "Bundled workflow skill synced: specode-do-work:" in result.stdout
    assert_sandbox_called(calls_log)


def test_invalid_options_fail_before_sandbox_execution(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    cases = [
        (("--max-iterations", "0"), "--max-iterations must be a positive integer"),
        (("--max-iterations", "abc"), "--max-iterations must be a positive integer"),
        (("--effort", "enormous"), "--effort must be one of: minimal, low, medium, high, xhigh"),
        (("--reasoning-effort", "enormous"), "--effort must be one of: minimal, low, medium, high, xhigh"),
        (("--max-iterations",), "--max-iterations requires a value"),
        (("--model",), "--model requires a value"),
        (("--effort",), "--effort requires a value"),
        (("--reasoning-effort",), "--reasoning-effort requires a value"),
        (("--prd",), "--prd requires a value"),
        (("--plan",), "--plan requires a value"),
        (("--unexpected-option",), "unknown argument: --unexpected-option"),
    ]
    for args, expected_error in cases:
        result = run_loop(project, *args, path=path)

        assert result.returncode == 1
        assert f"Error: {expected_error}" in result.stderr
        assert "Specode Loop preflight passed." not in result.stdout
        assert_sandbox_not_called(calls_log)


def test_project_option_must_be_first_argument(tmp_path: Path, monkeypatch) -> None:
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    result = run_loop(None, "--model", "test-model", path=path)

    assert result.returncode == 1
    assert "Error: project directory is required as the first argument" in result.stderr
    assert_sandbox_not_called(calls_log)


def test_missing_custom_planning_documents_fail_before_sandbox_execution(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "missing-custom-docs"
    project.mkdir()
    (project / "real-prd").write_text("# PRD\n", encoding="utf-8")
    (project / "real-plan").write_text("# Plan\n", encoding="utf-8")
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    missing_prd = run_loop(project, "--prd", "missing-prd", "--plan", "real-plan", path=path)
    assert missing_prd.returncode == 1
    assert f"Error: required PRD document is missing: {project / 'missing-prd'}" in missing_prd.stderr
    assert "Specode Loop preflight passed." not in missing_prd.stdout
    assert_sandbox_not_called(calls_log)

    missing_plan = run_loop(project, "--prd", "real-prd", "--plan", "missing-plan", path=path)
    assert missing_plan.returncode == 1
    assert f"Error: required plan document is missing: {project / 'missing-plan'}" in missing_plan.stderr
    assert "Specode Loop preflight passed." not in missing_plan.stdout
    assert_sandbox_not_called(calls_log)


def test_relative_planning_document_paths_cannot_escape_project(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "containment-relative")
    outside_prd = tmp_path / "outside-prd"
    outside_plan = tmp_path / "outside-plan"
    outside_prd.write_text("# Outside PRD\n", encoding="utf-8")
    outside_plan.write_text("# Outside Plan\n", encoding="utf-8")
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    prd_result = run_loop(project, "--prd", "../outside-prd", path=path)
    assert prd_result.returncode == 1
    assert "Error: selected PRD document must resolve inside the Target Project:" in prd_result.stderr
    assert "Specode Loop preflight passed." not in prd_result.stdout
    assert_bundled_skill_not_synced(project)
    assert_sandbox_not_called(calls_log)

    plan_result = run_loop(project, "--plan", "../outside-plan", path=path)
    assert plan_result.returncode == 1
    assert "Error: selected plan document must resolve inside the Target Project:" in plan_result.stderr
    assert "Specode Loop preflight passed." not in plan_result.stdout
    assert_bundled_skill_not_synced(project)
    assert_sandbox_not_called(calls_log)


def test_absolute_planning_document_paths_cannot_escape_project(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "containment-absolute")
    outside_prd = tmp_path / "absolute-outside-prd"
    outside_plan = tmp_path / "absolute-outside-plan"
    outside_prd.write_text("# Outside PRD\n", encoding="utf-8")
    outside_plan.write_text("# Outside Plan\n", encoding="utf-8")
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    prd_result = run_loop(project, "--prd", str(outside_prd), path=path)
    assert prd_result.returncode == 1
    assert "Error: selected PRD document must resolve inside the Target Project:" in prd_result.stderr
    assert "Specode Loop preflight passed." not in prd_result.stdout
    assert_bundled_skill_not_synced(project)
    assert_sandbox_not_called(calls_log)

    plan_result = run_loop(project, "--plan", str(outside_plan), path=path)
    assert plan_result.returncode == 1
    assert "Error: selected plan document must resolve inside the Target Project:" in plan_result.stderr
    assert "Specode Loop preflight passed." not in plan_result.stdout
    assert_bundled_skill_not_synced(project)
    assert_sandbox_not_called(calls_log)


def test_planning_document_symlinks_cannot_resolve_outside_project(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "containment-symlink")
    outside_prd = tmp_path / "symlink-target-prd"
    outside_prd.write_text("# Outside PRD\n", encoding="utf-8")
    linked_prd = project / "linked-prd"
    linked_prd.symlink_to(outside_prd)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    result = run_loop(project, "--prd", "linked-prd", path=path)

    assert result.returncode == 1
    assert "Error: selected PRD document must resolve inside the Target Project:" in result.stderr
    assert "Specode Loop preflight passed." not in result.stdout
    assert_bundled_skill_not_synced(project)
    assert_sandbox_not_called(calls_log)


def test_missing_runtime_prerequisites_fail_before_sandbox_execution(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    result = run_loop(project, path="")

    assert result.returncode == 1
    assert "Error: Docker Sandbox CLI 'sbx' is not installed or not on PATH" in result.stderr

    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

    missing_prd = tmp_path / "missing-prd"
    missing_prd.mkdir()
    (missing_prd / "plan.md").write_text("# Plan\n", encoding="utf-8")
    result = run_loop(missing_prd, path=path)
    assert result.returncode == 1
    assert "required PRD document is missing" in result.stderr
    assert_sandbox_not_called(calls_log)

    missing_plan = tmp_path / "missing-plan"
    missing_plan.mkdir()
    (missing_plan / "prd.md").write_text("# PRD\n", encoding="utf-8")
    result = run_loop(missing_plan, path=path)
    assert result.returncode == 1
    assert "required plan document is missing" in result.stderr
    assert_sandbox_not_called(calls_log)


def test_runtime_code_uses_only_standard_library_imports() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    runtime_imports = {
        alias.name.split(".", 1)[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    runtime_imports |= {
        node.module.split(".", 1)[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "typer" not in runtime_imports
    assert "rich" not in runtime_imports
    assert runtime_imports <= set(sys.stdlib_module_names)
