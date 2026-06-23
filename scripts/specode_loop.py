from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


MAX_ITERATIONS_DEFAULT = "10"
ALLOWED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
RUNNER_SKILLS_REL = Path(".agents") / "skills"
SPECODE_REQUIRED_SKILLS = ("specode-do-work",)
SPECODE_WORKFLOW_SKILL = "specode-do-work"
TASK_DONE_SENTINEL = "TASK DONE"
ALL_TASKS_DONE_SENTINEL = "ALL TASKS DONE"
FAILURE_EXCERPT_LINES = 30


@dataclass
class Options:
    project_dir: str
    max_iterations: str = MAX_ITERATIONS_DEFAULT
    model: str = ""
    reasoning_effort: str = ""


@dataclass
class LoopState:
    active_sandbox: str = ""
    temp_output: Path | None = None
    last_message_output: Path | None = None
    log_file: Path | None = None
    last_sentinel: str = ""


def usage() -> str:
    return """Usage: scripts/specode_loop.py PROJECT_DIR [options]

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
"""


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def log_line(state: LoopState, message: str = "", *, terminal: bool = True) -> None:
    if terminal:
        print(message)
    if state.log_file is not None:
        with state.log_file.open("a", encoding="utf-8") as log:
            log.write(f"{message}\n")


def parse_args(argv: list[str]) -> Options:
    if not argv:
        print(usage(), file=sys.stderr, end="")
        raise SystemExit(2)

    first = argv[0]
    if first in {"-h", "--help"}:
        print(usage(), end="")
        raise SystemExit(0)
    if first.startswith("-"):
        fail("project directory is required as the first argument")

    options = Options(project_dir=first)
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--max-iterations":
            if index + 1 >= len(argv):
                fail("--max-iterations requires a value")
            options.max_iterations = argv[index + 1]
            index += 2
        elif arg == "--model":
            if index + 1 >= len(argv):
                fail("--model requires a value")
            options.model = argv[index + 1]
            index += 2
        elif arg in {"--effort", "--reasoning-effort"}:
            if index + 1 >= len(argv):
                fail(f"{arg} requires a value")
            options.reasoning_effort = argv[index + 1]
            index += 2
        elif arg in {"-h", "--help"}:
            print(usage(), end="")
            raise SystemExit(0)
        else:
            fail(f"unknown argument: {arg}")

    return options


def validate_positive_integer(name: str, value: str) -> None:
    if not value or value.startswith("0") or any(char < "0" or char > "9" for char in value):
        fail(f"{name} must be a positive integer")


def validate_reasoning_effort(value: str) -> None:
    if value and value not in ALLOWED_REASONING_EFFORTS:
        fail("--effort must be one of: minimal, low, medium, high, xhigh")


def resolve_project_dir(project_dir: str) -> Path:
    path = Path(project_dir)
    try:
        project_abs = path.resolve(strict=True)
    except FileNotFoundError:
        fail(f"project directory does not exist: {project_dir}")
    except OSError:
        fail(f"project directory does not exist: {project_dir}")
    if not project_abs.is_dir():
        fail(f"project directory does not exist: {project_dir}")
    return project_abs


def runner_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sync_required_bundled_skills(project_abs: Path, root: Path | None = None) -> list[str]:
    root = runner_root() if root is None else root
    source_root = root / RUNNER_SKILLS_REL
    target_root = project_abs / RUNNER_SKILLS_REL
    synced_skills: list[str] = []

    for skill_name in SPECODE_REQUIRED_SKILLS:
        source_dir = source_root / skill_name
        target_dir = target_root / skill_name

        if not source_dir.is_dir():
            fail(f"bundled workflow skill directory is missing: {source_dir}")

        if source_dir.resolve() != target_dir.resolve():
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            if target_dir.exists():
                if target_dir.is_dir() and not target_dir.is_symlink():
                    shutil.rmtree(target_dir)
                else:
                    target_dir.unlink()
            shutil.copytree(source_dir, target_dir)

        synced_skills.append(f"{skill_name}:{target_dir}")

    return synced_skills


def git_command(project_abs: Path, *args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_abs), *args],
        stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )


def warn_for_existing_git_state(project_abs: Path) -> None:
    in_work_tree = git_command(project_abs, "rev-parse", "--is-inside-work-tree")
    if in_work_tree.returncode != 0:
        warn(f"{project_abs} is not inside a Git work tree. Continuing.")
        return

    has_unstaged_changes = git_command(project_abs, "diff", "--quiet", "--ignore-submodules", "--").returncode == 1
    untracked = git_command(project_abs, "ls-files", "--others", "--exclude-standard", capture_output=True)
    if untracked.stdout:
        has_unstaged_changes = True

    if has_unstaged_changes:
        warn(f"{project_abs} has existing unstaged changes. Continuing.")

    staged = git_command(project_abs, "diff", "--cached", "--quiet", "--ignore-submodules", "--")
    if staged.returncode == 1:
        warn(f"{project_abs} has existing staged changes. Continuing.")


def preflight(options: Options) -> tuple[Path, list[str]]:
    validate_positive_integer("--max-iterations", options.max_iterations)
    validate_reasoning_effort(options.reasoning_effort)

    if shutil.which("sbx") is None:
        fail("Docker Sandbox CLI 'sbx' is not installed or not on PATH")

    project_abs = resolve_project_dir(options.project_dir)
    prd_abs = project_abs / "prd.md"
    plan_abs = project_abs / "plan.md"

    if not prd_abs.is_file():
        fail(f"required PRD file is missing: {prd_abs}")
    if not plan_abs.is_file():
        fail(f"required plan file is missing: {plan_abs}")

    warn_for_existing_git_state(project_abs)
    synced_skills = sync_required_bundled_skills(project_abs)

    print("Specode Loop preflight passed.")
    print(f"Project: {project_abs}")
    print("Workspace mode: direct (sandbox edits apply to this working tree)")
    print(f"PRD: {prd_abs}")
    print(f"Plan: {plan_abs}")
    for synced_skill in synced_skills:
        print(f"Bundled workflow skill synced: {synced_skill}")
    print(f"Max iterations: {options.max_iterations}")
    if options.model:
        print(f"Model: {options.model}")
    else:
        print("Model: Codex/project default")
    if options.reasoning_effort:
        print(f"Reasoning effort: {options.reasoning_effort}")
    else:
        print("Reasoning effort: Codex/project default")
    return project_abs, synced_skills


def write_preflight_log(state: LoopState, project_abs: Path, options: Options, synced_skills: list[str]) -> None:
    log_line(state, "Specode Loop preflight passed.", terminal=False)
    log_line(state, f"Project: {project_abs}", terminal=False)
    log_line(state, "Workspace mode: direct (sandbox edits apply to this working tree)", terminal=False)
    log_line(state, f"PRD: {project_abs / 'prd.md'}", terminal=False)
    log_line(state, f"Plan: {project_abs / 'plan.md'}", terminal=False)
    for synced_skill in synced_skills:
        log_line(state, f"Bundled workflow skill synced: {synced_skill}", terminal=False)
    log_line(state, f"Verbose transcript logging: {os.environ.get('SPECODE_LOOP_VERBOSE', '0')}", terminal=False)
    log_line(state, f"Max iterations: {options.max_iterations}", terminal=False)
    if options.model:
        log_line(state, f"Model: {options.model}", terminal=False)
    else:
        log_line(state, "Model: Codex/project default", terminal=False)
    if options.reasoning_effort:
        log_line(state, f"Reasoning effort: {options.reasoning_effort}", terminal=False)
    else:
        log_line(state, "Reasoning effort: Codex/project default", terminal=False)


def sanitize_name_part(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]", "-", value).lower().strip("-")
    return sanitized or "project"


def new_sandbox_name(project_abs: Path, iteration: int) -> str:
    project_name = sanitize_name_part(project_abs.name)
    project_name = project_name[:20].rstrip("-") or "project"
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"specode-loop-{project_name}-{run_stamp}-{iteration:02d}-{os.getpid()}"
    return name[:63].rstrip("-")


def build_prompt(project_abs: Path) -> str:
    return f"""You are running non-interactively inside Docker Sandbox.

Project root:
{project_abs}

Use the project-local {SPECODE_WORKFLOW_SKILL} skill.

Read prd.md and plan.md before choosing work.

Work on AFK Phases only. Do not work on HITL Phases.

Select exactly one undone AFK Phase in plan.md for this run.
Complete only the selected AFK Phase.
Mark the completed AFK Phase done in plan.md by changing its checkbox from "[ ]" to "[x]".

If no undone AFK Phases remain, output exactly:
{ALL_TASKS_DONE_SENTINEL}

When the selected AFK Phase is complete and plan.md has been updated, output exactly:
{TASK_DONE_SENTINEL}

Blocked or incomplete work must not output a success sentinel.
"""


def make_temp_output(iteration: int) -> Path:
    tmp_dir = os.environ.get("TMPDIR") or "/tmp"
    handle = tempfile.NamedTemporaryFile(prefix=f"specode_loop.{iteration}.", dir=tmp_dir, delete=False)
    handle.close()
    return Path(handle.name)


def cleanup_temp_output(state: LoopState) -> None:
    for path_attr in ("temp_output", "last_message_output"):
        path = getattr(state, path_attr)
        if path is not None and path.exists():
            path.unlink()
        setattr(state, path_attr, None)


def cleanup_active_sandbox(state: LoopState, *, terminal: bool = False, report_no_active: bool = False) -> None:
    if not state.active_sandbox:
        if report_no_active:
            log_line(state, "Sandbox cleanup: no active sandbox to remove.", terminal=terminal)
        return

    sandbox_name = state.active_sandbox
    result = subprocess.run(
        ["sbx", "rm", sandbox_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    state.active_sandbox = ""
    if result.returncode == 0:
        message = f"Sandbox cleanup: removed sandbox {sandbox_name}."
    else:
        message = f"Sandbox cleanup: failed to remove sandbox {sandbox_name} (exit code: {result.returncode})."
    log_line(state, message, terminal=terminal)


def install_interrupt_handlers(state: LoopState) -> None:
    def handle_interrupt(_signum: int, _frame: object) -> None:
        print("\nInterrupted.", file=sys.stderr)
        cleanup_temp_output(state)
        cleanup_active_sandbox(state, terminal=True, report_no_active=True)
        raise SystemExit(130)

    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)


def contains_exact_line(path: Path | None, sentinel: str) -> bool:
    if path is None or not path.exists():
        return False
    return any(line.rstrip("\n") == sentinel for line in path.read_text(encoding="utf-8").splitlines())


def sentinel_detected(state: LoopState, sentinel: str) -> bool:
    return contains_exact_line(state.temp_output, sentinel) or contains_exact_line(state.last_message_output, sentinel)


def append_last_message(state: LoopState) -> None:
    if state.last_message_output is None or not state.last_message_output.exists():
        return
    if state.last_message_output.stat().st_size == 0:
        return

    if os.environ.get("SPECODE_LOOP_VERBOSE", "0") == "1":
        log_line(state, "===== Codex final message captured from --output-last-message =====")
        content = state.last_message_output.read_text(encoding="utf-8")
        print(content, end="")
        if not content.endswith("\n"):
            print()
        if state.log_file is not None:
            with state.log_file.open("a", encoding="utf-8") as log:
                log.write(content)
                if not content.endswith("\n"):
                    log.write("\n")
    else:
        log_line(state, "Captured Codex final message from --output-last-message.")

    if state.temp_output is not None:
        with state.temp_output.open("a", encoding="utf-8") as temp_output:
            temp_output.write(state.last_message_output.read_text(encoding="utf-8"))
            temp_output.write("\n")


def tail_lines(path: Path | None, count: int) -> list[str]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[-count:]


def print_no_sentinel_failure_summary(
    state: LoopState,
    *,
    iteration: int,
    max_iterations: str,
    command_status: int,
    sandbox_name: str,
) -> None:
    lines = [
        "",
        "Sandbox iteration failed without a success sentinel.",
        f"Iteration: {iteration}/{max_iterations}",
        f"Sandbox: {sandbox_name}",
        f"Sandbox command exit code: {command_status}",
        "Expected success sentinels:",
        f"- {TASK_DONE_SENTINEL}",
        f"- {ALL_TASKS_DONE_SENTINEL}",
        f"Project log: {state.log_file}",
        f"Last {FAILURE_EXCERPT_LINES} captured output lines:",
    ]
    excerpt = tail_lines(state.temp_output, FAILURE_EXCERPT_LINES)
    lines.extend(excerpt if excerpt else ["(no output captured)"])
    lines.append("For the full raw transcript, rerun with SPECODE_LOOP_VERBOSE=1.")
    for line in lines:
        log_line(state, line)


def stream_sandbox_command(command: list[str], state: LoopState) -> int:
    assert state.temp_output is not None
    verbose = os.environ.get("SPECODE_LOOP_VERBOSE", "0") == "1"
    with state.temp_output.open("w", encoding="utf-8") as temp_output:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            temp_output.write(line)
            temp_output.flush()
            if verbose and state.log_file is not None:
                with state.log_file.open("a", encoding="utf-8") as log:
                    log.write(line)
        return process.wait()


def run_single_task_iteration(project_abs: Path, options: Options, state: LoopState, iteration: int) -> bool:
    state.last_sentinel = ""
    state.active_sandbox = new_sandbox_name(project_abs, iteration)
    sandbox_name = state.active_sandbox
    state.temp_output = make_temp_output(iteration)
    state.last_message_output = project_abs / f".specode_loop-last-message.{iteration}.{os.getpid()}"
    if state.last_message_output.exists():
        state.last_message_output.unlink()

    codex_args = [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-C",
        str(project_abs),
    ]
    if options.model:
        codex_args.extend(["-m", options.model])
    if options.reasoning_effort:
        codex_args.extend(["-c", f'model_reasoning_effort="{options.reasoning_effort}"'])
    codex_args.extend(["-o", str(state.last_message_output), build_prompt(project_abs)])

    log_line(state)
    log_line(
        state,
        f"===== Specode Loop iteration {iteration}/{options.max_iterations} | {timestamp()} | sandbox: {sandbox_name} =====",
    )
    log_line(state, "Starting non-interactive Codex run in Docker Sandbox direct workspace mode.")

    command = ["sbx", "run", "--name", sandbox_name, "codex", str(project_abs), "--", *codex_args]
    command_status = stream_sandbox_command(command, state)
    append_last_message(state)

    if sentinel_detected(state, ALL_TASKS_DONE_SENTINEL):
        log_line(
            state,
            f"===== iteration {iteration} status: ALL TASKS DONE sentinel detected; overall run complete (command exit code: {command_status}) =====",
        )
        state.last_sentinel = "all"
        cleanup_temp_output(state)
        return True

    if sentinel_detected(state, TASK_DONE_SENTINEL):
        log_line(
            state,
            f"===== iteration {iteration} status: TASK DONE sentinel detected; iteration successful (command exit code: {command_status}) =====",
        )
        state.last_sentinel = "task"
        cleanup_temp_output(state)
        return True

    log_line(
        state,
        f"===== iteration {iteration} status: FAILED, no exact success sentinel detected (command exit code: {command_status}) =====",
    )
    print_no_sentinel_failure_summary(
        state,
        iteration=iteration,
        max_iterations=options.max_iterations,
        command_status=command_status,
        sandbox_name=sandbox_name,
    )
    state.last_sentinel = "none"
    cleanup_temp_output(state)
    return False


def run_loop(project_abs: Path, options: Options, state: LoopState) -> int:
    for iteration in range(1, int(options.max_iterations) + 1):
        if run_single_task_iteration(project_abs, options, state, iteration):
            cleanup_active_sandbox(state)
            if state.last_sentinel == "all":
                return 0
            continue

        cleanup_active_sandbox(state, terminal=True)
        return 1

    log_line(state)
    log_line(state, "Specode Loop stopped at the maximum iteration cap.")
    log_line(state, f"Configured maximum iterations reached: {options.max_iterations}")
    log_line(
        state,
        f"Stop reason: reached max iterations ({options.max_iterations}) before {ALL_TASKS_DONE_SENTINEL}.",
    )
    log_line(state, f"{ALL_TASKS_DONE_SENTINEL} was not observed.")
    log_line(state, f"Project log: {state.log_file}")
    return 1


def main(argv: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if argv is None else argv)
    state = LoopState()
    install_interrupt_handlers(state)
    try:
        project_abs, synced_skills = preflight(options)
        state.log_file = project_abs / "specode_loop.log"
        write_preflight_log(state, project_abs, options, synced_skills)
        return run_loop(project_abs, options, state)
    finally:
        cleanup_temp_output(state)
        cleanup_active_sandbox(state)


if __name__ == "__main__":
    raise SystemExit(main())
