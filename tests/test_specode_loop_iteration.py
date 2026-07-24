import json
import os
import re
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from specode_loop_iteration import (  # noqa: E402
    SandboxIterationOutcome,
    SandboxIterationRequest,
    run_sandbox_iteration,
)


def _install_fake_sbx(tmp_path: Path) -> tuple[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_log = tmp_path / "sbx-calls.jsonl"
    fake_sbx = bin_dir / "sbx"
    fake_sbx.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['FAKE_SBX_CALLS']).open('a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "contract_log = os.environ.get('FAKE_SBX_CONTRACT_LOG')\n"
        "if contract_log:\n"
        "    with Path(contract_log).open('a', encoding='utf-8') as log:\n"
        "        log.write(json.dumps({\n"
        "            'command': args[0],\n"
        "            'stdin': sys.stdin.read(),\n"
        "            'openai_api_key': os.environ.get('OPENAI_API_KEY'),\n"
        "            'codex_api_key': os.environ.get('CODEX_API_KEY'),\n"
        "            'preserved': os.environ.get('FAKE_SBX_PRESERVED'),\n"
        "        }) + '\\n')\n"
        "if args[0] == 'create':\n"
        "    print(os.environ.get('FAKE_SBX_CREATE_OUTPUT', 'sandbox created'))\n"
        "    resource = os.environ.get('FAKE_SBX_RESOURCE')\n"
        "    if resource and os.environ.get('FAKE_SBX_CREATE_RESOURCE') == '1':\n"
        "        Path(resource).write_text(args[2], encoding='utf-8')\n"
        "    raise SystemExit(int(os.environ.get('FAKE_SBX_CREATE_STATUS', '0')))\n"
        "elif args[0] == 'exec':\n"
        "    print(os.environ.get('FAKE_SBX_EXEC_OUTPUT', 'streamed Codex progress'))\n"
        "    stderr_output = os.environ.get('FAKE_SBX_EXEC_STDERR')\n"
        "    if stderr_output:\n"
        "        print(stderr_output, file=sys.stderr)\n"
        "    output_path = Path(args[args.index('-o') + 1])\n"
        "    final_message = os.environ.get('FAKE_SBX_FINAL_MESSAGE', 'ALL TASKS DONE\\n')\n"
        "    if os.environ.get('FAKE_SBX_FINAL_MESSAGE_DIRECTORY') == '1':\n"
        "        output_path.mkdir()\n"
        "    elif os.environ.get('FAKE_SBX_FINAL_MESSAGE_BROKEN_SYMLINK') == '1':\n"
        "        output_path.symlink_to(output_path.with_name('missing-final-message'))\n"
        "    elif final_message:\n"
        "        output_path.write_text(final_message, encoding='utf-8')\n"
        "    if os.environ.get('FAKE_SBX_TRANSCRIPT_DIRECTORY') == '1':\n"
        "        transcript = next(Path(os.environ['TMPDIR']).glob('specode_loop.*'))\n"
        "        transcript.unlink()\n"
        "        transcript.mkdir()\n"
        "    if os.environ.get('FAKE_SBX_REMOVE_EXECUTABLE') == '1':\n"
        "        Path(sys.argv[0]).unlink()\n"
        "    raise SystemExit(int(os.environ.get('FAKE_SBX_EXEC_STATUS', '0')))\n"
        "elif args[0] == 'rm':\n"
        "    observations = os.environ.get('FAKE_SBX_ARTIFACT_OBSERVATIONS')\n"
        "    if observations:\n"
        "        project = Path(os.environ['FAKE_SBX_TARGET_PROJECT'])\n"
        "        tmp_dir = Path(os.environ['TMPDIR'])\n"
        "        Path(observations).write_text(json.dumps({\n"
        "            'final_messages': sorted(path.name for path in project.glob('.specode_loop-last-message.*')),\n"
        "            'transcripts': sorted(path.name for path in tmp_dir.glob('specode_loop.*')),\n"
        "        }), encoding='utf-8')\n"
        "    resource = os.environ.get('FAKE_SBX_RESOURCE')\n"
        "    if resource:\n"
        "        Path(resource).unlink(missing_ok=True)\n"
        "    raise SystemExit(int(os.environ.get('FAKE_SBX_RM_STATUS', '0')))\n"
        "else:\n"
        "    raise SystemExit(127)\n",
        encoding="utf-8",
    )
    fake_sbx.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", calls_log


def _prepare_iteration_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SandboxIterationRequest:
    project = tmp_path / "project"
    project.mkdir()
    (project / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (project / "plan.md").write_text("# Plan\n", encoding="utf-8")
    log_file = project / "specode_loop.log"
    log_file.write_text("", encoding="utf-8")
    path, calls_log = _install_fake_sbx(tmp_path)
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return SandboxIterationRequest(
        target_project=project.resolve(),
        prd_role_path=Path("prd.md"),
        plan_role_path=Path("plan.md"),
        iteration=1,
        maximum_iterations=3,
        model="test-model",
        reasoning_effort="high",
        project_log=log_file,
        verbose_transcript=False,
    )


def test_one_complete_iteration_reports_all_tasks_done_and_releases_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project_with_a_long_name"
    project.mkdir()
    (project / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (project / "plan.md").write_text("# Plan\n", encoding="utf-8")
    log_file = project / "specode_loop.log"
    log_file.write_text("", encoding="utf-8")
    path, calls_log = _install_fake_sbx(tmp_path)
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    request = SandboxIterationRequest(
        target_project=project.resolve(),
        prd_role_path=Path("prd.md"),
        plan_role_path=Path("plan.md"),
        iteration=1,
        maximum_iterations=3,
        model="test-model",
        reasoning_effort="high",
        project_log=log_file,
        verbose_transcript=False,
    )

    with pytest.raises(FrozenInstanceError):
        request.iteration = 2  # type: ignore[misc]

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    assert "streamed Codex progress" in capsys.readouterr().out

    calls = [
        json.loads(line) for line in calls_log.read_text(encoding="utf-8").splitlines()
    ]
    assert len(calls) == 3
    create, execute, remove = calls
    sandbox_name = create[2]
    assert create == ["create", "--name", sandbox_name, "codex", str(project)]
    assert len(sandbox_name) <= 63
    assert re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", sandbox_name)
    assert execute[:4] == ["exec", sandbox_name, "codex", "exec"]
    assert execute[4:9] == [
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-C",
        str(project),
        "-m",
    ]
    assert execute[9:13] == [
        "test-model",
        "-c",
        'model_reasoning_effort="high"',
        "-o",
    ]
    prompt = execute[-1]
    assert "Invoke the $do-work skill if it is available in this sandbox." in prompt
    assert "PRD document: prd.md" in prompt
    assert "Plan document: plan.md" in prompt
    assert (
        "If no undone AFK Plan Tasks remain, output exactly:\nALL TASKS DONE" in prompt
    )
    assert remove == ["rm", "--force", sandbox_name]
    assert not list(tmp_path.glob("specode_loop.*"))
    assert not list(project.glob(".specode_loop-last-message.*"))


def test_exact_task_done_reports_one_plan_task_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (project / "plan.md").write_text("# Plan\n", encoding="utf-8")
    log_file = project / "specode_loop.log"
    log_file.write_text("", encoding="utf-8")
    path, calls_log = _install_fake_sbx(tmp_path)
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", "TASK DONE\n")
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    outcome = run_sandbox_iteration(
        SandboxIterationRequest(
            target_project=project.resolve(),
            prd_role_path=Path("prd.md"),
            plan_role_path=Path("plan.md"),
            iteration=1,
            maximum_iterations=3,
            model="test-model",
            reasoning_effort="high",
            project_log=log_file,
            verbose_transcript=False,
        )
    )

    assert outcome is SandboxIterationOutcome.PLAN_TASK_COMPLETED


@pytest.mark.parametrize(
    "final_message",
    [
        "The words TASK DONE are present, but not alone.\n",
        "TASK DONE later\n",
        " ALL TASKS DONE\n",
    ],
)
def test_inexact_success_sentinel_text_reports_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_message: str,
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", final_message)

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.FAILED


@pytest.mark.parametrize(
    ("final_message", "expected"),
    [
        ("TASK DONE\n", SandboxIterationOutcome.PLAN_TASK_COMPLETED),
        ("ordinary final message\n", SandboxIterationOutcome.FAILED),
    ],
)
def test_nonempty_final_message_is_authoritative_over_echoed_prompt_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_message: str,
    expected: SandboxIterationOutcome,
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "FAKE_SBX_EXEC_OUTPUT",
        "If no undone AFK Plan Tasks remain, output exactly:\nALL TASKS DONE",
    )
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", final_message)

    outcome = run_sandbox_iteration(request)

    assert outcome is expected


def test_streamed_transcript_is_authoritative_when_final_message_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_EXEC_OUTPUT", "progress\nTASK DONE")
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", "")

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.PLAN_TASK_COMPLETED


def test_all_tasks_done_takes_precedence_when_both_exact_sentinels_appear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", "TASK DONE\nALL TASKS DONE\n")

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED


@pytest.mark.parametrize(
    ("command", "status", "sentinel", "expected"),
    [
        ("exec", "42", "TASK DONE\n", SandboxIterationOutcome.PLAN_TASK_COMPLETED),
        (
            "create",
            "23",
            "ALL TASKS DONE",
            SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED,
        ),
        ("exec", "7", "still working\n", SandboxIterationOutcome.FAILED),
    ],
)
def test_success_sentinel_remains_authoritative_regardless_of_command_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    status: str,
    sentinel: str,
    expected: SandboxIterationOutcome,
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv(f"FAKE_SBX_{command.upper()}_STATUS", status)
    if command == "create":
        monkeypatch.setenv("FAKE_SBX_CREATE_OUTPUT", sentinel)
    else:
        monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", sentinel)

    outcome = run_sandbox_iteration(request)

    assert outcome is expected


def test_every_sbx_command_isolated_from_runner_stdin_and_api_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    contract_log = tmp_path / "sbx-contract.jsonl"
    monkeypatch.setenv("FAKE_SBX_CONTRACT_LOG", str(contract_log))
    monkeypatch.setenv("FAKE_SBX_PRESERVED", "still-present")
    monkeypatch.setenv("OPENAI_API_KEY", "runner-openai-key")
    monkeypatch.setenv("CODEX_API_KEY", "runner-codex-key")

    saved_stdin = os.dup(0)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"runner standard input")
        os.close(write_fd)
        os.dup2(read_fd, 0)
        os.close(read_fd)
        outcome = run_sandbox_iteration(request)
    finally:
        os.dup2(saved_stdin, 0)
        os.close(saved_stdin)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    contracts = [
        json.loads(line)
        for line in contract_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [contract["command"] for contract in contracts] == [
        "create",
        "exec",
        "rm",
    ]
    assert all(contract["stdin"] == "" for contract in contracts)
    assert all(contract["openai_api_key"] is None for contract in contracts)
    assert all(contract["codex_api_key"] is None for contract in contracts)
    assert all(contract["preserved"] == "still-present" for contract in contracts)


def test_custom_request_values_reach_codex_in_the_command_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    custom_request = SandboxIterationRequest(
        target_project=request.target_project,
        prd_role_path=Path("planning/product.md"),
        plan_role_path=Path("delivery/work-items.md"),
        iteration=1,
        maximum_iterations=3,
        model="custom-model",
        reasoning_effort="xhigh",
        project_log=request.project_log,
        verbose_transcript=False,
    )

    outcome = run_sandbox_iteration(custom_request)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    calls_log = Path(os.environ["FAKE_SBX_CALLS"])
    calls = [
        json.loads(line) for line in calls_log.read_text(encoding="utf-8").splitlines()
    ]
    execute = calls[1]
    sandbox_name = calls[0][2]
    final_message = request.target_project / (
        f".specode_loop-last-message.1.{os.getpid()}"
    )
    expected_prompt = f"""You are running non-interactively inside Docker Sandbox.

Project root:
{request.target_project}

Invoke the $do-work skill if it is available in this sandbox.
If the preferred copy is unavailable, invoke $do-work from the project-local .agents/skills/specode-do-work directory.

PRD document: planning/product.md
Plan document: delivery/work-items.md

The PRD document corresponds to output from the global $to-spec skill.
The plan document corresponds to output from the global $to-tickets skill.
For $do-work, treat each unchecked numbered ticket in a $to-tickets plan as a Phase.

Read the PRD document and plan document before choosing work.

Work on AFK Plan Tasks only. Do not work on HITL Plan Tasks.

If no undone AFK Plan Tasks remain, output exactly:
ALL TASKS DONE

When the selected AFK Plan Task is complete and the plan document has been updated, output exactly:
TASK DONE

Blocked or incomplete work must not output a success sentinel.
"""
    assert execute == [
        "exec",
        sandbox_name,
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-C",
        str(request.target_project),
        "-m",
        "custom-model",
        "-c",
        'model_reasoning_effort="xhigh"',
        "-o",
        str(final_message),
        expected_prompt,
    ]


def test_standard_error_is_merged_into_streamed_standard_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_EXEC_STDERR", "Codex diagnostic from stderr")

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    captured = capsys.readouterr()
    assert "Codex diagnostic from stderr" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "partially_created",
    [False, True],
)
def test_failed_creation_skips_codex_and_removes_the_assigned_sandbox_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partially_created: bool,
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    resource = tmp_path / "fake-sandbox-resource"
    monkeypatch.setenv("FAKE_SBX_CREATE_STATUS", "19")
    monkeypatch.setenv("FAKE_SBX_RESOURCE", str(resource))
    if partially_created:
        monkeypatch.setenv("FAKE_SBX_CREATE_RESOURCE", "1")

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.FAILED
    calls_log = Path(os.environ["FAKE_SBX_CALLS"])
    calls = [
        json.loads(line) for line in calls_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [call[0] for call in calls] == ["create", "rm"]
    assert calls[1] == ["rm", "--force", calls[0][2]]
    assert not resource.exists()


def test_concise_reporting_captures_final_message_without_raw_output_in_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_EXEC_OUTPUT", "RAW TRANSCRIPT: internal work details")
    monkeypatch.setenv(
        "FAKE_SBX_FINAL_MESSAGE", "RAW FINAL MESSAGE: plan summary\nALL TASKS DONE\n"
    )

    outcome = run_sandbox_iteration(request)

    terminal = capsys.readouterr().out
    log = request.project_log.read_text(encoding="utf-8")
    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    assert "RAW TRANSCRIPT: internal work details" in terminal
    assert "Captured Codex final message from --output-last-message." in terminal
    assert "RAW TRANSCRIPT:" not in log
    assert "RAW FINAL MESSAGE:" not in log
    assert "Captured Codex final message from --output-last-message." in log
    assert "ALL TASKS DONE sentinel detected" in log
    assert "Sandbox cleanup: removed sandbox " not in terminal
    assert "Sandbox cleanup: removed sandbox " in log


def test_verbose_reporting_includes_raw_transcript_and_final_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    request = SandboxIterationRequest(
        target_project=request.target_project,
        prd_role_path=request.prd_role_path,
        plan_role_path=request.plan_role_path,
        iteration=request.iteration,
        maximum_iterations=request.maximum_iterations,
        model=request.model,
        reasoning_effort=request.reasoning_effort,
        project_log=request.project_log,
        verbose_transcript=True,
    )
    monkeypatch.setenv(
        "FAKE_SBX_EXEC_OUTPUT", "RAW TRANSCRIPT: detailed sandbox output"
    )
    monkeypatch.setenv(
        "FAKE_SBX_FINAL_MESSAGE",
        "RAW FINAL MESSAGE: detailed final note\nALL TASKS DONE\n",
    )

    outcome = run_sandbox_iteration(request)

    terminal = capsys.readouterr().out
    log = request.project_log.read_text(encoding="utf-8")
    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    heading = "===== Codex final message captured from --output-last-message ====="
    assert heading in terminal
    assert "RAW FINAL MESSAGE: detailed final note" in terminal
    assert "RAW TRANSCRIPT: detailed sandbox output" in log
    assert heading in log
    assert "RAW FINAL MESSAGE: detailed final note" in log


def test_failure_reporting_includes_bounded_evidence_before_visible_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    output = "\n".join(f"agent output line {line:02d}" for line in range(1, 36))
    monkeypatch.setenv("FAKE_SBX_EXEC_OUTPUT", output)
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE", "")
    monkeypatch.setenv("FAKE_SBX_EXEC_STATUS", "7")

    outcome = run_sandbox_iteration(request)

    terminal = capsys.readouterr().out
    log = request.project_log.read_text(encoding="utf-8")
    assert outcome is SandboxIterationOutcome.FAILED
    assert "FAILED, no exact success sentinel detected" in terminal
    assert "Sandbox iteration failed without a success sentinel." in terminal
    assert "Iteration: 1/3" in terminal
    assert "Sandbox command exit code: 7" in terminal
    assert "Expected success sentinels:\n- TASK DONE\n- ALL TASKS DONE" in terminal
    assert f"Project log: {request.project_log}" in terminal
    assert "Last 30 captured output lines:" in terminal
    assert "agent output line 06" in terminal
    assert "agent output line 35" in terminal
    assert "agent output line 05" not in log
    assert "For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1." in terminal
    cleanup = "Sandbox cleanup: removed sandbox "
    assert cleanup in terminal
    assert (
        terminal.index("FAILED, no exact success sentinel detected")
        < terminal.index("Sandbox iteration failed without a success sentinel.")
        < terminal.index(cleanup)
    )
    assert "Sandbox iteration failed without a success sentinel." in log
    assert cleanup in log


def test_failed_cleanup_is_visible_without_replacing_successful_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_RM_STATUS", "23")

    outcome = run_sandbox_iteration(request)

    terminal = capsys.readouterr().out
    log = request.project_log.read_text(encoding="utf-8")
    failure = "Sandbox cleanup: failed to remove sandbox "
    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    assert failure in terminal
    assert "(exit code: 23)." in terminal
    assert failure in log
    assert "(exit code: 23)." in log


def test_artifact_cleanup_failure_does_not_skip_sandbox_removal_or_replace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE_DIRECTORY", "1")

    with pytest.raises(IsADirectoryError) as raised:
        run_sandbox_iteration(request)

    calls = [
        json.loads(line)
        for line in Path(os.environ["FAKE_SBX_CALLS"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [call[0] for call in calls] == ["create", "exec", "rm"]
    assert ".specode_loop-last-message" in str(raised.value.filename)
    assert "Artifact cleanup: failed to remove artifact " in capsys.readouterr().out


def test_attempt_artifacts_are_absent_before_forced_sandbox_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    observations = tmp_path / "artifact-observations.json"
    monkeypatch.setenv("FAKE_SBX_ARTIFACT_OBSERVATIONS", str(observations))
    monkeypatch.setenv("FAKE_SBX_TARGET_PROJECT", str(request.target_project))

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    assert json.loads(observations.read_text(encoding="utf-8")) == {
        "final_messages": [],
        "transcripts": [],
    }


def test_process_start_failure_releases_artifacts_and_preserves_the_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    with pytest.raises(FileNotFoundError) as raised:
        run_sandbox_iteration(request)

    assert raised.value.filename == "sbx"
    assert not list(tmp_path.glob("specode_loop.*"))
    assert not list(request.target_project.glob(".specode_loop-last-message.*"))
    assert "Sandbox cleanup: failed to remove sandbox " in capsys.readouterr().out


def test_sandbox_cleanup_start_failure_does_not_replace_classified_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_REMOVE_EXECUTABLE", "1")
    monkeypatch.setenv("PATH", os.environ["PATH"].split(os.pathsep)[0])

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
    assert not list(tmp_path.glob("specode_loop.*"))
    assert not list(request.target_project.glob(".specode_loop-last-message.*"))
    terminal = capsys.readouterr().out
    assert "Sandbox cleanup: failed to remove sandbox " in terminal
    assert "FileNotFoundError" in terminal


def test_later_cleanup_stages_continue_after_the_first_artifact_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    observations = tmp_path / "artifact-observations.json"
    monkeypatch.setenv("FAKE_SBX_TRANSCRIPT_DIRECTORY", "1")
    monkeypatch.setenv("FAKE_SBX_ARTIFACT_OBSERVATIONS", str(observations))
    monkeypatch.setenv("FAKE_SBX_TARGET_PROJECT", str(request.target_project))

    with pytest.raises(IsADirectoryError) as raised:
        run_sandbox_iteration(request)

    observed = json.loads(observations.read_text(encoding="utf-8"))
    assert "specode_loop." in str(raised.value.filename)
    assert observed["final_messages"] == []
    assert len(observed["transcripts"]) == 1
    calls = [
        json.loads(line)
        for line in Path(os.environ["FAKE_SBX_CALLS"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [call[0] for call in calls] == ["create", "exec", "rm"]


def test_broken_artifact_symlink_is_removed_during_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _prepare_iteration_request(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_FINAL_MESSAGE_BROKEN_SYMLINK", "1")

    outcome = run_sandbox_iteration(request)

    assert outcome is SandboxIterationOutcome.FAILED
    assert not list(request.target_project.glob(".specode_loop-last-message.*"))
