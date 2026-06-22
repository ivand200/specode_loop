import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RUNNER = ROOT_DIR / "scripts" / "specode_loop.py"


def run_loop(
    project: Path | None = None,
    *args: str,
    path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(RUNNER)]
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
