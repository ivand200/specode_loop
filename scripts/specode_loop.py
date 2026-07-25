from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from specode_loop_iteration import (
    SandboxIterationOutcome,
    SandboxIterationRequest,
    run_sandbox_iteration,
)

MAX_ITERATIONS_DEFAULT = "12"
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_REASONING_EFFORT = "medium"
ALLOWED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
DEFAULT_AUTH_MODE = "oauth"
ALLOWED_AUTH_MODES = {"oauth", "api-key"}
API_KEY_ENVIRONMENT_VARIABLES = ("OPENAI_API_KEY", "CODEX_API_KEY")
WORKFLOW_KIT_REL = Path("sandbox-kits") / "workflow-skills"
WORKFLOW_SKILL_REL = (
    Path("files")
    / "home"
    / ".agents"
    / "skills"
    / "specode-loop-implement"
)
WORKFLOW_KIT_ANCHORS = (
    Path("spec.yaml"),
    WORKFLOW_SKILL_REL / "SKILL.md",
    WORKFLOW_SKILL_REL / "agents" / "openai.yaml",
)
MINIMUM_SBX_VERSION = (0, 37, 0)
MAX_VALIDATOR_DIAGNOSTIC_CHARS = 800
DEFAULT_PRD_DOCUMENT = Path("prd.md")
DEFAULT_PLAN_DOCUMENT = Path("plan.md")
ALL_TASKS_DONE_SENTINEL = "ALL TASKS DONE"


@dataclass
class Options:
    project_dir: str
    max_iterations: str = MAX_ITERATIONS_DEFAULT
    model: str = DEFAULT_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    auth_mode: str = DEFAULT_AUTH_MODE
    prd: str = str(DEFAULT_PRD_DOCUMENT)
    plan: str = str(DEFAULT_PLAN_DOCUMENT)


@dataclass(frozen=True)
class PlanningDocuments:
    prd_abs: Path
    plan_abs: Path
    prd_role_path: Path
    plan_role_path: Path


@dataclass
class LoopState:
    log_file: Path | None = None


def usage() -> str:
    return """Usage: scripts/specode_loop.py PROJECT_DIR [options]

Run Specode Loop for a project with selected planning documents.

Arguments:
  PROJECT_DIR              Target Project directory

Options:
  --prd PATH               PRD document path (default: prd.md)
  --plan PATH              Plan document path (default: plan.md)
  --max-iterations N       Maximum sandbox iterations to run (default: 12)
  --auth MODE              OpenAI authentication: oauth, api-key (default: oauth)
  --model MODEL            Model for the sandboxed Codex run (default: gpt-5.6-sol)
  --effort EFFORT          Reasoning effort: minimal, low, medium, high, xhigh (default: medium)
  --reasoning-effort EFFORT
                           Alias for --effort
  -h, --help               Show this help
"""


def fail(message: str) -> NoReturn:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


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
        elif arg == "--prd":
            if index + 1 >= len(argv):
                fail("--prd requires a value")
            options.prd = argv[index + 1]
            index += 2
        elif arg == "--plan":
            if index + 1 >= len(argv):
                fail("--plan requires a value")
            options.plan = argv[index + 1]
            index += 2
        elif arg == "--model":
            if index + 1 >= len(argv):
                fail("--model requires a value")
            options.model = argv[index + 1]
            index += 2
        elif arg == "--auth":
            if index + 1 >= len(argv):
                fail("--auth requires a value")
            options.auth_mode = argv[index + 1]
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
    if (
        not value
        or value.startswith("0")
        or any(char < "0" or char > "9" for char in value)
    ):
        fail(f"{name} must be a positive integer")


def validate_reasoning_effort(value: str) -> None:
    if value and value not in ALLOWED_REASONING_EFFORTS:
        fail("--effort must be one of: minimal, low, medium, high, xhigh")


def validate_auth_mode(value: str) -> None:
    if value not in ALLOWED_AUTH_MODES:
        fail("--auth must be one of: oauth, api-key")


def sbx_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for variable in API_KEY_ENVIRONMENT_VARIABLES:
        environment.pop(variable, None)
    return environment


def detect_global_openai_auth_mode() -> str:
    result = subprocess.run(
        ["sbx", "secret", "ls", "-g", "--service", "openai"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=sbx_environment(),
    )
    if result.returncode != 0:
        detail = result.stderr.strip()
        suffix = f": {detail}" if detail else ""
        fail(f"could not inspect Docker Sandbox OpenAI credentials{suffix}")

    openai_rows = [
        line for line in result.stdout.splitlines() if "openai" in line.lower()
    ]
    if not openai_rows:
        fail(
            "no global OpenAI credential is configured; OAuth is the default. "
            "Run: sbx secret set -g openai --oauth"
        )

    secret_field = openai_rows[-1].split()[-1].lower()
    return "api-key" if secret_field.startswith(("sk-", "sk_")) else "oauth"


def validate_configured_auth_mode(requested_mode: str) -> None:
    configured_mode = detect_global_openai_auth_mode()
    if requested_mode == "oauth" and configured_mode == "api-key":
        fail(
            "OAuth authentication is required by default, but Docker Sandbox has "
            "an OpenAI API key configured. Replace it with OAuth using: "
            "sbx secret set -g openai --oauth. To deliberately use the stored "
            "API key, pass --auth api-key."
        )
    if requested_mode == "api-key" and configured_mode != "api-key":
        fail(
            "API-key authentication was requested, but Docker Sandbox does not "
            "have an OpenAI API key configured. Run: sbx secret set -g openai"
        )


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


def resolve_planning_document(
    project_abs: Path, role: str, value: str
) -> tuple[Path, Path]:
    configured_path = Path(value)
    selected_path = (
        configured_path
        if configured_path.is_absolute()
        else project_abs / configured_path
    )

    try:
        resolved_path = selected_path.resolve(strict=True)
    except FileNotFoundError:
        fail(f"required {role} document is missing: {selected_path}")
    except OSError:
        fail(f"required {role} document is missing: {selected_path}")

    if not resolved_path.is_file():
        fail(f"required {role} document is missing: {selected_path}")

    try:
        role_path = resolved_path.relative_to(project_abs)
    except ValueError:
        fail(
            f"selected {role} document must resolve inside the Target Project: {selected_path}"
        )
    return resolved_path, role_path


def resolve_planning_documents(
    project_abs: Path, options: Options
) -> PlanningDocuments:
    prd_abs, prd_role_path = resolve_planning_document(project_abs, "PRD", options.prd)
    plan_abs, plan_role_path = resolve_planning_document(
        project_abs, "plan", options.plan
    )

    return PlanningDocuments(
        prd_abs=prd_abs,
        plan_abs=plan_abs,
        prd_role_path=prd_role_path,
        plan_role_path=plan_role_path,
    )


def runner_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_sbx_preflight_command(
    sbx: str, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sbx, *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=sbx_environment(),
    )


def semantic_version_text(version: tuple[int, int, int] | None) -> str:
    if version is None:
        return "unavailable"
    return ".".join(str(part) for part in version)


def fail_sbx_compatibility(
    check: str, observed_version: tuple[int, int, int] | None = None
) -> None:
    minimum = semantic_version_text(MINIMUM_SBX_VERSION)
    fail(
        f"Docker Sandbox compatibility failure: {check}; "
        f"observed version {semantic_version_text(observed_version)}; "
        f"minimum version {minimum}; upgrade Docker Sandbox and retry"
    )


def fail_invalid_workflow_kit(workflow_kit: Path, problem: str) -> None:
    fail(
        f"invalid Workflow Kit: {problem}: {workflow_kit}; "
        "the checked-in Specode Loop Workflow Kit is damaged or incompatible; "
        "restore or reinstall the checked-in kit and retry"
    )


def bounded_validator_diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    diagnostic = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
    diagnostic = re.sub(r"\s+", " ", diagnostic)
    if len(diagnostic) > MAX_VALIDATOR_DIAGNOSTIC_CHARS:
        return f"{diagnostic[:MAX_VALIDATOR_DIAGNOSTIC_CHARS]}..."
    return diagnostic


def validate_workflow_kit() -> Path:
    configured_kit = runner_root() / WORKFLOW_KIT_REL
    try:
        workflow_kit = configured_kit.resolve(strict=True)
    except OSError:
        fail_invalid_workflow_kit(
            configured_kit, "required directory is missing"
        )
    if not workflow_kit.is_dir():
        fail_invalid_workflow_kit(
            configured_kit, "required directory is missing"
        )

    for anchor in WORKFLOW_KIT_ANCHORS:
        anchor_path = workflow_kit / anchor
        if not anchor_path.is_file():
            fail_invalid_workflow_kit(
                workflow_kit, f"required file is missing: {anchor_path}"
            )

    sbx = shutil.which("sbx")
    if sbx is None:
        fail_sbx_compatibility(
            "CLI discovery failed because Docker Sandbox CLI 'sbx' is not installed or not on PATH"
        )

    try:
        version_result = run_sbx_preflight_command(sbx, "version")
    except OSError:
        fail_sbx_compatibility("version check could not be launched")
    version_match = re.search(
        r"(?<![0-9])v?([0-9]+)\.([0-9]+)\.([0-9]+)(?![0-9])",
        version_result.stdout,
    )
    version: tuple[int, int, int] | None = None
    if version_match is not None:
        major, minor, patch = version_match.groups()
        version = (int(major), int(minor), int(patch))
    if version_result.returncode != 0:
        fail_sbx_compatibility("version check exited unsuccessfully", version)
    if version is None:
        fail_sbx_compatibility("version check returned no semantic version")
    if version < MINIMUM_SBX_VERSION:
        fail_sbx_compatibility("version check found an unsupported version", version)

    try:
        parser_result = run_sbx_preflight_command(
            sbx, "create", "--no-share-skills", "--help"
        )
    except OSError:
        fail_sbx_compatibility("create parser check could not be launched", version)
    if parser_result.returncode != 0:
        fail_sbx_compatibility(
            "create parser check rejected --no-share-skills", version
        )

    try:
        validator_result = run_sbx_preflight_command(
            sbx, "kit", "validate", str(workflow_kit)
        )
    except OSError:
        fail_sbx_compatibility("kit validator launch failed", version)
    if validator_result.returncode != 0:
        diagnostic = bounded_validator_diagnostic(validator_result)
        fail_invalid_workflow_kit(
            workflow_kit, f"Docker validation failed ({diagnostic})"
        )
    return workflow_kit


def git_command(
    project_abs: Path, *args: str, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
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

    has_unstaged_changes = (
        git_command(
            project_abs, "diff", "--quiet", "--ignore-submodules", "--"
        ).returncode
        == 1
    )
    untracked = git_command(
        project_abs, "ls-files", "--others", "--exclude-standard", capture_output=True
    )
    if untracked.stdout:
        has_unstaged_changes = True

    if has_unstaged_changes:
        warn(f"{project_abs} has existing unstaged changes. Continuing.")

    staged = git_command(
        project_abs, "diff", "--cached", "--quiet", "--ignore-submodules", "--"
    )
    if staged.returncode == 1:
        warn(f"{project_abs} has existing staged changes. Continuing.")


def preflight(
    options: Options,
) -> tuple[Path, PlanningDocuments, Path]:
    validate_positive_integer("--max-iterations", options.max_iterations)
    validate_reasoning_effort(options.reasoning_effort)
    validate_auth_mode(options.auth_mode)

    project_abs = resolve_project_dir(options.project_dir)
    planning_documents = resolve_planning_documents(project_abs, options)
    workflow_kit = validate_workflow_kit()
    validate_configured_auth_mode(options.auth_mode)

    warn_for_existing_git_state(project_abs)

    print("Specode Loop preflight passed.")
    print(f"Project: {project_abs}")
    print("Workspace mode: direct (sandbox edits apply to this working tree)")
    print(f"PRD document: {planning_documents.prd_abs}")
    print(f"Plan document: {planning_documents.plan_abs}")
    print(f"Workflow kit validated: {workflow_kit}")
    print(f"Max iterations: {options.max_iterations}")
    if options.auth_mode == "oauth":
        print("Authentication: OAuth")
    else:
        print("Authentication: API key (explicit opt-in)")
    if options.model:
        print(f"Model: {options.model}")
    else:
        print("Model: Codex/project default")
    if options.reasoning_effort:
        print(f"Reasoning effort: {options.reasoning_effort}")
    else:
        print("Reasoning effort: Codex/project default")
    return project_abs, planning_documents, workflow_kit


def write_preflight_log(
    state: LoopState,
    project_abs: Path,
    planning_documents: PlanningDocuments,
    options: Options,
    workflow_kit: Path,
) -> None:
    log_line(state, "Specode Loop preflight passed.", terminal=False)
    log_line(state, f"Project: {project_abs}", terminal=False)
    log_line(
        state,
        "Workspace mode: direct (sandbox edits apply to this working tree)",
        terminal=False,
    )
    log_line(state, f"PRD document: {planning_documents.prd_abs}", terminal=False)
    log_line(state, f"Plan document: {planning_documents.plan_abs}", terminal=False)
    log_line(state, f"Workflow kit validated: {workflow_kit}", terminal=False)
    log_line(
        state,
        f"Verbose transcript logging: {os.environ.get('SPECODE_LOOP_VERBOSE', '0')}",
        terminal=False,
    )
    log_line(state, f"Max iterations: {options.max_iterations}", terminal=False)
    if options.auth_mode == "oauth":
        log_line(state, "Authentication: OAuth", terminal=False)
    else:
        log_line(state, "Authentication: API key (explicit opt-in)", terminal=False)
    if options.model:
        log_line(state, f"Model: {options.model}", terminal=False)
    else:
        log_line(state, "Model: Codex/project default", terminal=False)
    if options.reasoning_effort:
        log_line(state, f"Reasoning effort: {options.reasoning_effort}", terminal=False)
    else:
        log_line(state, "Reasoning effort: Codex/project default", terminal=False)


def install_interrupt_handlers() -> None:
    def handle_interrupt(_signum: int, _frame: object) -> None:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)

    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)


def run_loop(
    project_abs: Path,
    planning_documents: PlanningDocuments,
    options: Options,
    state: LoopState,
    workflow_kit: Path,
) -> int:
    assert state.log_file is not None
    maximum_iterations = int(options.max_iterations)
    for iteration in range(1, int(options.max_iterations) + 1):
        outcome = run_sandbox_iteration(
            SandboxIterationRequest(
                target_project=project_abs,
                workflow_kit=workflow_kit,
                prd_role_path=planning_documents.prd_role_path,
                plan_role_path=planning_documents.plan_role_path,
                iteration=iteration,
                maximum_iterations=maximum_iterations,
                model=options.model,
                reasoning_effort=options.reasoning_effort,
                project_log=state.log_file,
                verbose_transcript=os.environ.get("SPECODE_LOOP_VERBOSE", "0") == "1",
            )
        )
        if outcome is SandboxIterationOutcome.PLAN_TASK_COMPLETED:
            continue
        if outcome is SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED:
            return 0
        if outcome is SandboxIterationOutcome.FAILED:
            return 1
        raise AssertionError(f"unsupported Sandbox Iteration outcome: {outcome!r}")

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
    install_interrupt_handlers()
    project_abs, planning_documents, workflow_kit = preflight(options)
    state.log_file = project_abs / "specode_loop.log"
    write_preflight_log(
        state,
        project_abs,
        planning_documents,
        options,
        workflow_kit,
    )
    return run_loop(project_abs, planning_documents, options, state, workflow_kit)


if __name__ == "__main__":
    raise SystemExit(main())
