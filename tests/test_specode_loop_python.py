import os
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
        "printf 'called|%s\\n' \"$*\" >>\"$FAKE_SBX_CALLS\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_sbx.chmod(0o755)
    path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return path, calls_log


def assert_sandbox_not_called(calls_log: Path) -> None:
    assert not calls_log.exists(), calls_log.read_text(encoding="utf-8") if calls_log.exists() else ""


def test_help_matches_shell_command_contract() -> None:
    result = run_loop(None, "--help")

    assert result.returncode == 0
    assert "Usage: scripts/specode_loop.py PROJECT_DIR [options]" in result.stdout
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


def test_option_parsing_and_valid_preflight_do_not_execute_sandbox(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))

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
    assert "Max iterations: 7" in result.stdout
    assert "Model: test-model" in result.stdout
    assert "Reasoning effort: medium" in result.stdout
    assert_sandbox_not_called(calls_log)


def test_bundled_skill_is_copied_and_owned_target_is_overwritten(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
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
    assert "name: specode-do-work" in copied_skill.read_text(encoding="utf-8")
    assert "stale local skill" not in copied_skill.read_text(encoding="utf-8")
    assert "Specode Loop runner workflow" in copied_reference.read_text(encoding="utf-8")
    assert not stale_file.exists()
    assert unrelated_skill.read_text(encoding="utf-8") == "project-owned skill\n"
    assert unrelated_agent_config.read_text(encoding="utf-8") == "project-owned agent config\n"
    assert_sandbox_not_called(calls_log)


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
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
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
    assert_sandbox_not_called(calls_log)


def test_hidden_user_skill_state_is_not_consulted(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex-home"))

    result = run_loop(project, path=path)

    copied_skill = project / ".agents" / "skills" / "specode-do-work" / "SKILL.md"
    assert result.returncode == 0
    assert copied_skill.read_text(encoding="utf-8") == (SPECODE_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "Bundled workflow skill synced: specode-do-work:" in result.stdout
    assert_sandbox_not_called(calls_log)


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
    assert "required PRD file is missing" in result.stderr
    assert_sandbox_not_called(calls_log)

    missing_plan = tmp_path / "missing-plan"
    missing_plan.mkdir()
    (missing_plan / "prd.md").write_text("# PRD\n", encoding="utf-8")
    result = run_loop(missing_plan, path=path)
    assert result.returncode == 1
    assert "required plan file is missing" in result.stderr
    assert_sandbox_not_called(calls_log)
