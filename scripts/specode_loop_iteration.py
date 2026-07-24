from __future__ import annotations

import os as _os
import re as _re
import subprocess as _subprocess
import tempfile as _tempfile
from dataclasses import dataclass as _dataclass
from datetime import datetime as _datetime
from enum import Enum as _Enum
from enum import auto as _auto
from pathlib import Path as _Path

__all__ = [
    "SandboxIterationRequest",
    "SandboxIterationOutcome",
    "run_sandbox_iteration",
]

_API_KEY_ENVIRONMENT_VARIABLES = ("OPENAI_API_KEY", "CODEX_API_KEY")
_PREFERRED_WORKFLOW_SKILL = "do-work"
_FALLBACK_WORKFLOW_SKILL = "specode-do-work"
_TASK_DONE_SENTINEL = "TASK DONE"
_ALL_TASKS_DONE_SENTINEL = "ALL TASKS DONE"


@_dataclass(frozen=True)
class SandboxIterationRequest:
    target_project: _Path
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
    run_stamp = _datetime.now().strftime("%Y%m%d-%H%M%S")
    name = (
        f"specode-loop-{project_name}-{run_stamp}-{iteration:02d}-{_os.getpid()}"
    )
    return name[:63].rstrip("-")


def _build_prompt(request: SandboxIterationRequest) -> str:
    return f"""You are running non-interactively inside Docker Sandbox.

Project root:
{request.target_project}

Invoke the ${_PREFERRED_WORKFLOW_SKILL} skill if it is available in this sandbox.
If the preferred copy is unavailable, invoke ${_PREFERRED_WORKFLOW_SKILL} from the project-local .agents/skills/{_FALLBACK_WORKFLOW_SKILL} directory.

PRD document: {request.prd_role_path}
Plan document: {request.plan_role_path}

The PRD document corresponds to output from the global $to-spec skill.
The plan document corresponds to output from the global $to-tickets skill.
For $do-work, treat each unchecked numbered ticket in a $to-tickets plan as a Phase.

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
    handle = _tempfile.NamedTemporaryFile(
        prefix=f"specode_loop.{iteration}.", dir=tmp_dir, delete=False
    )
    handle.close()
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
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            output.write(line)
            output.flush()
            if request.verbose_transcript:
                with request.project_log.open("a", encoding="utf-8") as log:
                    log.write(line)
        return process.wait()


def _contains_exact_line(path: _Path, sentinel: str) -> bool:
    if not path.exists():
        return False
    return any(
        line == sentinel
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def _remove_artifact(path: _Path) -> None:
    if path.exists():
        path.unlink()


def run_sandbox_iteration(
    request: SandboxIterationRequest,
) -> SandboxIterationOutcome:
    sandbox_name = _new_sandbox_name(request.target_project, request.iteration)
    transcript = _make_temp_output(request.iteration)
    final_message = request.target_project / (
        f".specode_loop-last-message.{request.iteration}.{_os.getpid()}"
    )
    _remove_artifact(final_message)

    command_status = 0
    outcome = SandboxIterationOutcome.FAILED
    try:
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
            "--name",
            sandbox_name,
            "codex",
            str(request.target_project),
        ]
        command_status = _stream_sandbox_command(create_command, request, transcript)
        if command_status == 0:
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

        authoritative_output = transcript
        if final_message.exists() and final_message.stat().st_size > 0:
            authoritative_output = final_message

        if _contains_exact_line(authoritative_output, _ALL_TASKS_DONE_SENTINEL):
            _log_line(
                request,
                f"===== iteration {request.iteration} status: ALL TASKS DONE sentinel detected; overall run complete (command exit code: {command_status}) =====",
            )
            outcome = SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED
        return outcome
    finally:
        _remove_artifact(transcript)
        _remove_artifact(final_message)
        cleanup = _subprocess.run(
            ["sbx", "rm", "--force", sandbox_name],
            stdin=_subprocess.DEVNULL,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            text=True,
            check=False,
            env=_sandbox_environment(),
        )
        if cleanup.returncode == 0:
            message = f"Sandbox cleanup: removed sandbox {sandbox_name}."
        else:
            message = (
                f"Sandbox cleanup: failed to remove sandbox {sandbox_name} "
                f"(exit code: {cleanup.returncode})."
            )
        with request.project_log.open("a", encoding="utf-8") as log:
            log.write(f"{message}\n")
