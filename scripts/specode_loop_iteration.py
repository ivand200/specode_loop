from __future__ import annotations

import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
from dataclasses import dataclass as _dataclass
from datetime import datetime as _datetime
from enum import Enum as _Enum
from enum import auto as _auto
from pathlib import Path as _Path

__all__ = [
    "SandboxIterationOutcome",
    "SandboxIterationRequest",
    "run_sandbox_iteration",
]

_API_KEY_ENVIRONMENT_VARIABLES = ("OPENAI_API_KEY", "CODEX_API_KEY")
_TASK_DONE_SENTINEL = "TASK DONE"
_ALL_TASKS_DONE_SENTINEL = "ALL TASKS DONE"
_FAILURE_EXCERPT_LINES = 30
_ALLOWED_REASONING_EFFORTS = {"", "minimal", "low", "medium", "high", "xhigh"}


@_dataclass(frozen=True)
class SandboxIterationRequest:
    target_project: _Path
    workflow_kit: _Path
    prd_role_path: _Path
    plan_role_path: _Path
    iteration: int
    maximum_iterations: int
    model: str
    reasoning_effort: str
    project_log: _Path
    verbose_transcript: bool


class SandboxIterationOutcome(_Enum):
    PLAN_TASK_COMPLETED = _auto()
    ALL_PLAN_TASKS_COMPLETED = _auto()
    FAILED = _auto()


def _validate_request(request: SandboxIterationRequest) -> None:
    if not 1 <= request.iteration <= request.maximum_iterations:
        raise ValueError("iteration must be between 1 and maximum_iterations inclusive")
    try:
        resolved_target_project = request.target_project.resolve(strict=True)
    except OSError as error:
        raise ValueError("Target Project must exist and be resolved") from error
    if (
        request.target_project != resolved_target_project
        or not resolved_target_project.is_dir()
    ):
        raise ValueError("Target Project must be an existing resolved directory")
    try:
        resolved_workflow_kit = request.workflow_kit.resolve(strict=True)
    except OSError as error:
        raise ValueError(
            "Workflow Kit must be an existing resolved directory"
        ) from error
    if (
        request.workflow_kit != resolved_workflow_kit
        or not resolved_workflow_kit.is_dir()
    ):
        raise ValueError("Workflow Kit must be an existing resolved directory")
    for role, role_path in (
        ("prd", request.prd_role_path),
        ("plan", request.plan_role_path),
    ):
        if role_path.is_absolute():
            raise ValueError(f"{role} role path must be Target Project-relative")
        resolved_role_path = (resolved_target_project / role_path).resolve()
        try:
            resolved_role_path.relative_to(resolved_target_project)
        except ValueError as error:
            raise ValueError(
                f"{role} role path must resolve inside the Target Project"
            ) from error
    if not request.project_log.is_file():
        raise ValueError("project log must be an initialized writable file")
    try:
        with request.project_log.open("a", encoding="utf-8"):
            pass
    except OSError as error:
        raise ValueError("project log must be an initialized writable file") from error
    if not isinstance(request.model, str) or "\0" in request.model:
        raise ValueError("model must be a validated string choice")
    if (
        not isinstance(request.reasoning_effort, str)
        or request.reasoning_effort not in _ALLOWED_REASONING_EFFORTS
    ):
        raise ValueError(
            "reasoning_effort must be one of: minimal, low, medium, high, xhigh"
        )


def _timestamp() -> str:
    return _datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def _log_line(request: SandboxIterationRequest, message: str = "") -> None:
    print(message)
    with request.project_log.open("a", encoding="utf-8") as log:
        log.write(f"{message}\n")


def _sanitize_name_part(value: str) -> str:
    sanitized = _re.sub(r"[^A-Za-z0-9]", "-", value).lower().strip("-")
    return sanitized or "project"


def _new_sandbox_name(target_project: _Path, iteration: int) -> str:
    project_name = _sanitize_name_part(target_project.name)
    project_name = project_name[:20].rstrip("-") or "project"
    run_stamp = _datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    name = f"specode-loop-{project_name}-{run_stamp}-{iteration:02d}-{_os.getpid()}"
    return name[:63].rstrip("-")


def _build_prompt(request: SandboxIterationRequest) -> str:
    return f"""You are running non-interactively inside Docker Sandbox.

Project root:
{request.target_project}

Use the `$specode-loop-implement` skill to execute this iteration.

PRD document: {request.prd_role_path}
Plan document: {request.plan_role_path}

Read the PRD document and plan document before choosing work.

Work on AFK Plan Tasks only. Do not work on HITL Plan Tasks.

If no undone AFK Plan Tasks remain, output exactly:
{_ALL_TASKS_DONE_SENTINEL}

When the selected AFK Plan Task is complete and the plan document has been updated, output exactly:
{_TASK_DONE_SENTINEL}

Blocked or incomplete work must not output a success sentinel.
"""


def _sandbox_environment() -> dict[str, str]:
    environment = _os.environ.copy()
    for variable in _API_KEY_ENVIRONMENT_VARIABLES:
        environment.pop(variable, None)
    return environment


def _make_temp_output(iteration: int) -> _Path:
    tmp_dir = _os.environ.get("TMPDIR") or "/tmp"
    with _tempfile.NamedTemporaryFile(
        prefix=f"specode_loop.{iteration}.", dir=tmp_dir, delete=False
    ) as handle:
        return _Path(handle.name)


def _stream_sandbox_command(
    command: list[str], request: SandboxIterationRequest, transcript: _Path
) -> int:
    with transcript.open("w", encoding="utf-8") as output:
        process = _subprocess.Popen(
            command,
            stdin=_subprocess.DEVNULL,
            stdout=_subprocess.PIPE,
            stderr=_subprocess.STDOUT,
            text=True,
            env=_sandbox_environment(),
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                output.write(line)
                output.flush()
                if request.verbose_transcript:
                    with request.project_log.open("a", encoding="utf-8") as log:
                        log.write(line)
            return process.wait()
        except BaseException:
            _terminate_and_reap(process)
            raise


def _terminate_and_reap(process: _subprocess.Popen[str]) -> None:
    try:
        if process.poll() is not None:
            return
    except BaseException:  # noqa: BLE001,S110 -- preserve the active exception.
        pass

    try:
        process.terminate()
    except BaseException:  # noqa: BLE001,S110 -- cleanup is best effort.
        pass

    try:
        process.wait(timeout=1)
        return
    except _subprocess.TimeoutExpired:
        pass
    except BaseException:  # noqa: BLE001,S110 -- continue with forced cleanup.
        pass

    killed = False
    try:
        process.kill()
        killed = True
    except BaseException:  # noqa: BLE001,S110 -- continue attempting to reap.
        pass

    try:
        if killed:
            process.wait()
        else:
            process.wait(timeout=0)
    except BaseException:  # noqa: BLE001,S110 -- cleanup must not mask the caller.
        pass


def _contains_exact_line(path: _Path, sentinel: str) -> bool:
    if not path.exists():
        return False
    return any(
        line == sentinel for line in path.read_text(encoding="utf-8").splitlines()
    )


def _remove_artifact(path: _Path) -> None:
    path.unlink(missing_ok=True)


def _cleanup_iteration(
    request: SandboxIterationRequest,
    outcome: SandboxIterationOutcome,
    transcript: _Path | None,
    final_message: _Path,
    sandbox_name: str,
) -> BaseException | None:
    cleanup_control_flow: BaseException | None = None
    artifacts = (final_message,) if transcript is None else (transcript, final_message)

    for artifact in artifacts:
        try:
            _remove_artifact(artifact)
        except BaseException as error:  # noqa: BLE001 -- preserve control flow.
            if not isinstance(error, Exception) and cleanup_control_flow is None:
                cleanup_control_flow = error
            try:
                _log_line(
                    request,
                    f"Artifact cleanup: failed to remove artifact {artifact} "
                    f"({type(error).__name__}: {error}).",
                )
            except BaseException as reporting_error:  # noqa: BLE001
                if (
                    not isinstance(reporting_error, Exception)
                    and cleanup_control_flow is None
                ):
                    cleanup_control_flow = reporting_error

    cleanup_status: int | None = None
    cleanup_error: BaseException | None = None
    try:
        cleanup = _subprocess.run(
            ["sbx", "rm", "--force", sandbox_name],
            stdin=_subprocess.DEVNULL,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            text=True,
            check=False,
            env=_sandbox_environment(),
        )
        cleanup_status = cleanup.returncode
    except BaseException as error:  # noqa: BLE001 -- cleanup must finish first.
        cleanup_error = error
        if not isinstance(error, Exception) and cleanup_control_flow is None:
            cleanup_control_flow = error

    if cleanup_error is not None:
        message = (
            f"Sandbox cleanup: failed to remove sandbox {sandbox_name} "
            f"({type(cleanup_error).__name__}: {cleanup_error})."
        )
    elif cleanup_status == 0:
        message = f"Sandbox cleanup: removed sandbox {sandbox_name}."
    else:
        message = (
            f"Sandbox cleanup: failed to remove sandbox {sandbox_name} "
            f"(exit code: {cleanup_status})."
        )

    try:
        if outcome is SandboxIterationOutcome.FAILED or cleanup_status != 0:
            _log_line(request, message)
        else:
            with request.project_log.open("a", encoding="utf-8") as log:
                log.write(f"{message}\n")
    except BaseException as reporting_error:  # noqa: BLE001
        if not isinstance(reporting_error, Exception) and cleanup_control_flow is None:
            cleanup_control_flow = reporting_error

    return cleanup_control_flow


def _report_final_message(
    request: SandboxIterationRequest, final_message: _Path, transcript: _Path
) -> None:
    if not final_message.exists() or final_message.stat().st_size == 0:
        return

    content = final_message.read_text(encoding="utf-8")
    if request.verbose_transcript:
        _log_line(
            request,
            "===== Codex final message captured from --output-last-message =====",
        )
        print(content, end="")
        if not content.endswith("\n"):
            print()
        with request.project_log.open("a", encoding="utf-8") as log:
            log.write(content)
            if not content.endswith("\n"):
                log.write("\n")
    else:
        _log_line(request, "Captured Codex final message from --output-last-message.")

    with transcript.open("a", encoding="utf-8") as output:
        output.write(content)
        output.write("\n")


def _report_no_sentinel_failure(
    request: SandboxIterationRequest,
    transcript: _Path,
    command_status: int,
    sandbox_name: str,
) -> None:
    captured_lines = transcript.read_text(encoding="utf-8").splitlines()
    lines = [
        "",
        "Sandbox iteration failed without a success sentinel.",
        f"Iteration: {request.iteration}/{request.maximum_iterations}",
        f"Sandbox: {sandbox_name}",
        f"Sandbox command exit code: {command_status}",
        "Expected success sentinels:",
        f"- {_TASK_DONE_SENTINEL}",
        f"- {_ALL_TASKS_DONE_SENTINEL}",
        f"Project log: {request.project_log}",
        f"Last {_FAILURE_EXCERPT_LINES} captured output lines:",
    ]
    lines.extend(
        captured_lines[-_FAILURE_EXCERPT_LINES:]
        if captured_lines
        else ["(no output captured)"]
    )
    lines.append("For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1.")
    for line in lines:
        _log_line(request, line)


def run_sandbox_iteration(
    request: SandboxIterationRequest,
) -> SandboxIterationOutcome:
    _validate_request(request)
    sandbox_name = _new_sandbox_name(request.target_project, request.iteration)
    transcript: _Path | None = None
    final_message = request.target_project / (
        f".specode_loop-last-message.{request.iteration}.{_os.getpid()}"
    )

    command_status = 0
    outcome = SandboxIterationOutcome.FAILED
    try:
        transcript = _make_temp_output(request.iteration)
        _remove_artifact(final_message)
        _log_line(request)
        _log_line(
            request,
            f"===== Specode Loop iteration {request.iteration}/{request.maximum_iterations} | {_timestamp()} | sandbox: {sandbox_name} =====",
        )
        _log_line(
            request,
            "Starting non-interactive Codex run in Docker Sandbox direct workspace mode.",
        )

        create_command = [
            "sbx",
            "create",
            "--no-share-skills",
            "--name",
            sandbox_name,
            "--kit",
            str(request.workflow_kit),
            "codex",
            str(request.target_project),
        ]
        command_status = _stream_sandbox_command(create_command, request, transcript)
        if command_status != 0:
            _log_line(
                request,
                f"===== iteration {request.iteration} status: FAILED, sandbox creation / Workflow Kit application failed (command exit code: {command_status}) =====",
            )
            return outcome

        codex_args = [
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "-C",
            str(request.target_project),
        ]
        if request.model:
            codex_args.extend(["-m", request.model])
        if request.reasoning_effort:
            codex_args.extend(
                ["-c", f'model_reasoning_effort="{request.reasoning_effort}"']
            )
        codex_args.extend(["-o", str(final_message), _build_prompt(request)])
        command_status = _stream_sandbox_command(
            ["sbx", "exec", sandbox_name, "codex", *codex_args],
            request,
            transcript,
        )

        _report_final_message(request, final_message, transcript)

        authoritative_output = transcript
        if final_message.exists() and final_message.stat().st_size > 0:
            authoritative_output = final_message

        if _contains_exact_line(authoritative_output, _ALL_TASKS_DONE_SENTINEL):
            _log_line(
                request,
                f"===== iteration {request.iteration} status: ALL TASKS DONE sentinel detected; overall run complete (command exit code: {command_status}) =====",
            )
            outcome = SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
        elif _contains_exact_line(authoritative_output, _TASK_DONE_SENTINEL):
            _log_line(
                request,
                f"===== iteration {request.iteration} status: TASK DONE sentinel detected; iteration successful (command exit code: {command_status}) =====",
            )
            outcome = SandboxIterationOutcome.PLAN_TASK_COMPLETED
        else:
            _log_line(
                request,
                f"===== iteration {request.iteration} status: FAILED, no exact success sentinel detected (command exit code: {command_status}) =====",
            )
            _report_no_sentinel_failure(
                request, transcript, command_status, sandbox_name
            )
        return outcome
    finally:
        primary_error = _sys.exception()
        cleanup_control_flow = _cleanup_iteration(
            request,
            outcome,
            transcript,
            final_message,
            sandbox_name,
        )
        if primary_error is None and cleanup_control_flow is not None:
            raise cleanup_control_flow
