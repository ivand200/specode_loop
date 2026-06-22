from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


MAX_ITERATIONS_DEFAULT = "10"
ALLOWED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}


@dataclass
class Options:
    project_dir: str
    max_iterations: str = MAX_ITERATIONS_DEFAULT
    model: str = ""
    reasoning_effort: str = ""


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


def preflight(options: Options) -> Path:
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

    print("Specode Loop preflight passed.")
    print(f"Project: {project_abs}")
    print("Workspace mode: direct (sandbox edits apply to this working tree)")
    print(f"PRD: {prd_abs}")
    print(f"Plan: {plan_abs}")
    print(f"Max iterations: {options.max_iterations}")
    if options.model:
        print(f"Model: {options.model}")
    else:
        print("Model: Codex/project default")
    if options.reasoning_effort:
        print(f"Reasoning effort: {options.reasoning_effort}")
    else:
        print("Reasoning effort: Codex/project default")
    print("Python runner preflight complete; sandbox execution is not implemented yet.")
    return project_abs


def main(argv: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if argv is None else argv)
    preflight(options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
