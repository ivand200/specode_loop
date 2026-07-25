import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RUNNER = ROOT_DIR / "scripts" / "specode_loop.py"
ITERATION_MODULE = ROOT_DIR / "scripts" / "specode_loop_iteration.py"
WORKFLOW_KIT = ROOT_DIR / "sandbox-kits" / "workflow-skills"
WORKFLOW_SKILL = (
    WORKFLOW_KIT
    / "files"
    / "home"
    / ".agents"
    / "skills"
    / "specode-loop-implement"
)
AUTH_E2E = ROOT_DIR / "tests" / "specode_loop_auth-e2e.sh"


def run_loop(
    project: Path | None = None,
    *args: str,
    path: str | None = None,
    runner: Path = RUNNER,
    input_text: str | None = None,
    codex_home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(runner)]
    if project is not None:
        command.append(str(project))
    command.extend(args)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home or ROOT_DIR / ".missing-test-codex-home")
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        env=env,
        text=True,
        input=input_text,
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


def make_global_do_work_skill(tmp_path: Path) -> Path:
    codex_home = tmp_path / "codex-home"
    skill_dir = codex_home / "skills" / "do-work"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: do-work\n"
        "description: Test global do-work skill.\n"
        "---\n"
        "\n"
        "# Test Global Do Work\n",
        encoding="utf-8",
    )
    (skill_dir / "notes.txt").write_text("copied from global skill\n", encoding="utf-8")
    return codex_home


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
        "if [[ \"${FAKE_SBX_RECORD_AUTH_ENV:-}\" == \"1\" ]]; then\n"
        "  printf 'auth-env|OPENAI_API_KEY=%s|CODEX_API_KEY=%s\\n' \"${OPENAI_API_KEY:-unset}\" \"${CODEX_API_KEY:-unset}\" >>\"$FAKE_SBX_CALLS\"\n"
        "fi\n"
        "case \"$cmd\" in\n"
        "  version)\n"
        "    printf 'version|%s\\n' \"$*\" >>\"$FAKE_SBX_CALLS\"\n"
        "    printf 'v0.37.0 (test build)\\n'\n"
        "    exit 0\n"
        "    ;;\n"
        "  kit)\n"
        "    printf 'kit|%s\\n' \"$*\" >>\"$FAKE_SBX_CALLS\"\n"
        "    if [[ \"${1:-}\" != \"validate\" || -z \"${2:-}\" ]]; then exit 127; fi\n"
        "    printf 'VALID: %s (directory)\\n' \"$2\"\n"
        "    exit 0\n"
        "    ;;\n"
        "  secret)\n"
        "    if [[ \"${1:-}\" != \"ls\" ]]; then\n"
        "      printf 'unexpected fake sbx secret command: %s\\n' \"$*\" >&2\n"
        "      exit 127\n"
        "    fi\n"
        "    if [[ -n \"${FAKE_SBX_DIR:-}\" && -f \"$FAKE_SBX_DIR/secret.status\" ]]; then exit \"$(cat \"$FAKE_SBX_DIR/secret.status\")\"; fi\n"
        "    printf 'SCOPE      SERVICE   SECRET\\n'\n"
        "    if [[ \"${FAKE_SBX_OPENAI_SECRET:-oauth}\" != \"missing\" ]]; then\n"
        "      printf '(global)   openai    %s\\n' \"${FAKE_SBX_OPENAI_SECRET:-oauth}\"\n"
        "    fi\n"
        "    exit 0\n"
        "    ;;\n"
        "  create)\n"
        "    if [[ \"${1:-}\" == \"--no-share-skills\" && \"${2:-}\" == \"--help\" ]]; then\n"
        "      printf 'create|%s\\n' \"$*\" >>\"$FAKE_SBX_CALLS\"\n"
        "      exit 0\n"
        "    fi\n"
        "    original_args=\"$*\"\n"
        "    name=\"\"\n"
        "    project=\"\"\n"
        "    while [[ $# -gt 0 ]]; do\n"
        "      case \"$1\" in\n"
        "        --no-share-skills) shift ;;\n"
        "        --name) name=\"${2:-}\"; shift 2 ;;\n"
        "        --kit) shift 2 ;;\n"
        "        codex) project=\"${2:-}\"; break ;;\n"
        "        *) shift ;;\n"
        "      esac\n"
        "    done\n"
        "    printf 'create|%s|%s\\n' \"$name\" \"$original_args\" >>\"$FAKE_SBX_CALLS\"\n"
        "    if [[ -n \"$project\" ]]; then\n"
        "      for skill_name in do-work specode-do-work; do\n"
        "        skill_path=\"$project/.agents/skills/$skill_name/SKILL.md\"\n"
        "        if [[ -f \"$skill_path\" ]]; then\n"
        "          printf 'skill-before-exec|%s|present\\n' \"$skill_path\" >>\"$FAKE_SBX_CALLS\"\n"
        "        else\n"
        "          printf 'skill-before-exec|%s|missing\\n' \"$skill_path\" >>\"$FAKE_SBX_CALLS\"\n"
        "        fi\n"
        "      done\n"
        "    fi\n"
        "    if [[ -f \"$FAKE_SBX_DIR/create.status\" ]]; then exit \"$(cat \"$FAKE_SBX_DIR/create.status\")\"; fi\n"
        "    exit 0\n"
        "    ;;\n"
        "  exec)\n"
        "    name=\"${1:-}\"\n"
        "    shift || true\n"
        "    count_file=\"$FAKE_SBX_DIR/count\"\n"
        "    count=0\n"
        "    if [[ -f \"$count_file\" ]]; then count=\"$(cat \"$count_file\")\"; fi\n"
        "    count=$((count + 1))\n"
        "    printf '%s\\n' \"$count\" >\"$count_file\"\n"
        "    printf 'exec|%s|%s\\n' \"$name\" \"$*\" >>\"$FAKE_SBX_CALLS\"\n"
        "    output_file=\"$FAKE_SBX_DIR/run_${count}.out\"\n"
        "    status_file=\"$FAKE_SBX_DIR/run_${count}.status\"\n"
        "    interrupt_file=\"$FAKE_SBX_DIR/run_${count}.interrupt\"\n"
        "    last_message_file=\"$FAKE_SBX_DIR/run_${count}.last\"\n"
        "    if [[ -f \"$output_file\" ]]; then cat \"$output_file\"; fi\n"
        "    if [[ \"${FAKE_SBX_ECHO_STDIN:-}\" == \"1\" ]]; then\n"
        "      stdin_payload=\"$(cat)\"\n"
        "      if [[ -n \"$stdin_payload\" ]]; then\n"
        "        printf 'stdin|%s\\n' \"$stdin_payload\" >>\"$FAKE_SBX_CALLS\"\n"
        "        printf 'STDIN:%s\\n' \"$stdin_payload\"\n"
        "      fi\n"
        "    fi\n"
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
        "    if [[ \"${1:-}\" != \"--force\" ]]; then\n"
        "      printf 'expected sbx rm --force, got: %s\\n' \"$*\" >&2\n"
        "      exit 64\n"
        "    fi\n"
        "    shift\n"
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


def write_interrupt(tmp_path: Path, run_number: int, output: str) -> None:
    (tmp_path / f"run_{run_number}.out").write_text(output, encoding="utf-8")
    (tmp_path / f"run_{run_number}.interrupt").write_text("interrupt\n", encoding="utf-8")


def assert_sandbox_not_called(calls_log: Path) -> None:
    if not calls_log.exists():
        return
    calls = calls_log.read_text(encoding="utf-8").splitlines()
    unexpected = [
        call
        for call in calls
        if call.startswith("exec|")
        or (call.startswith("create|") and call != "create|--no-share-skills --help")
    ]
    assert unexpected == []


def assert_bundled_skill_not_synced(project: Path) -> None:
    assert not (project / ".agents" / "skills" / "specode-do-work").exists()


def assert_sandbox_called(calls_log: Path) -> str:
    assert calls_log.exists()
    return calls_log.read_text(encoding="utf-8")


def assert_no_temp_artifacts(tmp_path: Path, project: Path) -> None:
    assert not list(tmp_path.glob("specode_loop.*"))
    assert not list(project.glob(".specode_loop-last-message.*"))


def test_help_describes_python_command_contract() -> None:
    result = run_loop(None, "--help")

    assert result.returncode == 0
    assert "Usage: scripts/specode_loop.py PROJECT_DIR [options]" in result.stdout
    assert "--prd PATH" in result.stdout
    assert "--plan PATH" in result.stdout
    assert "--max-iterations N" in result.stdout
    assert "--auth MODE" in result.stdout
    assert "oauth, api-key (default: oauth)" in result.stdout
    assert "--reasoning-effort EFFORT" in result.stdout
    assert result.stderr == ""


def test_runner_maps_preflight_values_to_one_deep_iteration_call_per_position(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path, "deep-cutover")
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    monkeypatch.setenv("FAKE_SBX_DIR", str(tmp_path))
    monkeypatch.setenv("SPECODE_LOOP_VERBOSE", "1")
    request_log = tmp_path / "iteration-requests.jsonl"
    monkeypatch.setenv("ITERATION_REQUEST_LOG", str(request_log))

    isolated_root = tmp_path / "isolated-runner"
    isolated_scripts = isolated_root / "scripts"
    isolated_scripts.mkdir(parents=True)
    isolated_runner = isolated_scripts / "specode_loop.py"
    shutil.copyfile(RUNNER, isolated_runner)
    workflow_kit = isolated_root / "sandbox-kits" / "workflow-skills"
    workflow_skill = (
        workflow_kit
        / "files"
        / "home"
        / ".agents"
        / "skills"
        / "specode-loop-implement"
    )
    (workflow_skill / "agents").mkdir(parents=True)
    (workflow_kit / "spec.yaml").write_text(
        'schemaVersion: "1"\nkind: mixin\nname: specode-loop-workflow-skills\n',
        encoding="utf-8",
    )
    (workflow_skill / "SKILL.md").write_text(
        "---\nname: specode-loop-implement\ndescription: test\n---\n",
        encoding="utf-8",
    )
    (workflow_skill / "agents" / "openai.yaml").write_text(
        "policy:\n  allow_implicit_invocation: true\n",
        encoding="utf-8",
    )
    (isolated_scripts / "specode_loop_iteration.py").write_text(
        "from dataclasses import asdict, dataclass\n"
        "from enum import Enum, auto\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class SandboxIterationRequest:\n"
        "    target_project: Path\n"
        "    workflow_kit: Path\n"
        "    prd_role_path: Path\n"
        "    plan_role_path: Path\n"
        "    iteration: int\n"
        "    maximum_iterations: int\n"
        "    model: str\n"
        "    reasoning_effort: str\n"
        "    project_log: Path\n"
        "    verbose_transcript: bool\n"
        "\n"
        "class SandboxIterationOutcome(Enum):\n"
        "    PLAN_TASK_COMPLETED = auto()\n"
        "    ALL_PLAN_TASKS_COMPLETED = auto()\n"
        "    FAILED = auto()\n"
        "\n"
        "def run_sandbox_iteration(request):\n"
        "    values = asdict(request)\n"
        "    values = {key: str(value) if isinstance(value, Path) else value for key, value in values.items()}\n"
        "    with open(os.environ['ITERATION_REQUEST_LOG'], 'a', encoding='utf-8') as log:\n"
        "        log.write(json.dumps(values) + '\\n')\n"
        "    if request.iteration == 1:\n"
        "        return SandboxIterationOutcome.PLAN_TASK_COMPLETED\n"
        "    return SandboxIterationOutcome.ALL_PLAN_TASKS_COMPLETED\n",
        encoding="utf-8",
    )

    result = run_loop(
        project,
        "--max-iterations",
        "3",
        "--model",
        "test-model",
        "--effort",
        "high",
        path=path,
        runner=isolated_runner,
    )

    requests = [json.loads(line) for line in request_log.read_text().splitlines()]
    assert result.returncode == 0
    assert requests == [
        {
            "target_project": str(project.resolve()),
            "workflow_kit": str(workflow_kit.resolve()),
            "prd_role_path": "prd.md",
            "plan_role_path": "plan.md",
            "iteration": 1,
            "maximum_iterations": 3,
            "model": "test-model",
            "reasoning_effort": "high",
            "project_log": str(project / "specode_loop.log"),
            "verbose_transcript": True,
        },
        {
            "target_project": str(project.resolve()),
            "workflow_kit": str(workflow_kit.resolve()),
            "prd_role_path": "prd.md",
            "plan_role_path": "plan.md",
            "iteration": 2,
            "maximum_iterations": 3,
            "model": "test-model",
            "reasoning_effort": "high",
            "project_log": str(project / "specode_loop.log"),
            "verbose_transcript": True,
        },
    ]
    calls = calls_log.read_text(encoding="utf-8") if calls_log.exists() else ""
    expected_evidence = f"Workflow kit validated: {workflow_kit.resolve()}"
    assert result.stdout.count(expected_evidence) == 1
    assert (project / "specode_loop.log").read_text(encoding="utf-8").count(
        expected_evidence
    ) == 1
    assert calls.splitlines()[:3] == [
        "version|",
        "create|--no-share-skills --help",
        f"kit|validate {workflow_kit.resolve()}",
    ]
    assert calls.count("create|") == 1
    assert "exec|" not in calls


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


def test_real_auth_e2e_is_mode_selectable_and_runs_one_codex_request() -> None:
    source = AUTH_E2E.read_text(encoding="utf-8")

    assert 'AUTH_MODE="${SPECODE_LOOP_AUTH_E2E_MODE:-oauth}"' in source
    assert '--max-iterations 1 --auth "$AUTH_MODE"' in source
    assert "## [x] Phase 1: Authentication request fixture" in source
    assert "ALL TASKS DONE sentinel detected" in source


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
    assert "Authentication: OAuth" in result.stdout
    assert "Model: test-model" in result.stdout
    assert "Reasoning effort: medium" in result.stdout
    calls = assert_sandbox_called(calls_log)
    assert "create|specode-loop-project-" in calls
    assert "--no-share-skills --name specode-loop-project-" in calls
    assert f"--kit {WORKFLOW_KIT} codex {project}" in calls
    assert "exec|specode-loop-project-" in calls
    assert f"codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C {project}" in calls
    log = (project / "specode_loop.log").read_text(encoding="utf-8")
    evidence = f"Workflow kit validated: {WORKFLOW_KIT}"
    assert result.stdout.count(evidence) == 1
    assert log.count(evidence) == 1
    assert f"PRD document: {project / 'prd.md'}" in log
    assert f"Plan document: {project / 'plan.md'}" in log
    assert "ALL TASKS DONE sentinel detected" in log
    assert "rm|specode-loop-project-" in rm_log.read_text(encoding="utf-8")
    assert_no_temp_artifacts(tmp_path, project)


def test_oauth_is_default_and_rejects_stored_api_key_before_sandbox_execution(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_OPENAI_SECRET", "sk-pro******...******test")

    result = run_loop(project, path=path)

    assert result.returncode == 1
    assert "Error: OAuth authentication is required by default" in result.stderr
    assert "sbx secret set -g openai --oauth" in result.stderr
    assert "--auth api-key" in result.stderr
    assert_bundled_skill_not_synced(project)
    assert_sandbox_not_called(calls_log)


def test_api_key_auth_requires_explicit_opt_in(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SBX_OPENAI_SECRET", "sk-pro******...******test")
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, "--auth", "api-key", path=path)

    assert result.returncode == 0
    assert "Authentication: API key (explicit opt-in)" in result.stdout
    assert "create|" in assert_sandbox_called(calls_log)


def test_selected_auth_mode_must_match_stored_openai_credential(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)

    api_key_result = run_loop(project, "--auth", "api-key", path=path)
    assert api_key_result.returncode == 1
    assert "Error: API-key authentication was requested" in api_key_result.stderr
    assert "sbx secret set -g openai" in api_key_result.stderr

    monkeypatch.setenv("FAKE_SBX_OPENAI_SECRET", "missing")
    oauth_result = run_loop(project, path=path)
    assert oauth_result.returncode == 1
    assert "Error: no global OpenAI credential is configured" in oauth_result.stderr
    assert "sbx secret set -g openai --oauth" in oauth_result.stderr
    assert_sandbox_not_called(calls_log)


def test_oauth_mode_does_not_pass_api_key_environment_to_sbx(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "host-openai-key")
    monkeypatch.setenv("CODEX_API_KEY", "host-codex-key")
    monkeypatch.setenv("FAKE_SBX_RECORD_AUTH_ENV", "1")
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, path=path)

    assert result.returncode == 0
    calls = assert_sandbox_called(calls_log)
    assert "auth-env|OPENAI_API_KEY=unset|CODEX_API_KEY=unset" in calls


def test_default_model_and_reasoning_effort_are_passed_to_codex(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "defaults")
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, path=path)

    calls = assert_sandbox_called(calls_log)
    assert result.returncode == 0
    assert "Model: gpt-5.6-sol" in result.stdout
    assert "Reasoning effort: medium" in result.stdout
    assert (
        f"codex exec --dangerously-bypass-approvals-and-sandbox "
        f"--skip-git-repo-check -C {project} -m gpt-5.6-sol -c "
        f"model_reasoning_effort=\"medium\" -o {project}/.specode_loop-last-message."
    ) in calls


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
    assert calls.count("create|specode-loop-multi-step-") == 2
    assert calls.count("exec|specode-loop-multi-step-") == 2
    assert rm_log.read_text(encoding="utf-8").count("rm|specode-loop-multi-step-") == 2
    assert_no_temp_artifacts(tmp_path, project)


def test_failed_sandbox_iteration_maps_to_runner_failure_status(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path, "no-sentinel")
    path, _calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ordinary output without a sentinel\n", status=7)

    result = run_loop(project, path=path)

    assert result.returncode == 1
    assert "Sandbox iteration failed without a success sentinel." in result.stdout


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


def test_successful_provisioning_leaves_target_project_agent_files_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")
    project_do_work = project / ".agents" / "skills" / "do-work" / "SKILL.md"
    project_service_skill = (
        project / ".agents" / "skills" / "specode-loop-implement" / "SKILL.md"
    )
    unrelated_skill = project / ".agents" / "skills" / "project-owned" / "SKILL.md"
    unrelated_agent_config = project / ".agents" / "README.md"

    project_do_work.parent.mkdir(parents=True)
    project_do_work.write_text("project do-work\n", encoding="utf-8")
    project_service_skill.parent.mkdir(parents=True)
    project_service_skill.write_text("project service override\n", encoding="utf-8")
    unrelated_skill.parent.mkdir(parents=True)
    unrelated_skill.write_text("project-owned skill\n", encoding="utf-8")
    unrelated_agent_config.write_text("project-owned agent config\n", encoding="utf-8")
    before = {
        path.relative_to(project / ".agents"): path.read_bytes()
        for path in (project / ".agents").rglob("*")
        if path.is_file()
    }

    result = run_loop(project, path=path)

    assert result.returncode == 0
    after = {
        file.relative_to(project / ".agents"): file.read_bytes()
        for file in (project / ".agents").rglob("*")
        if file.is_file()
    }
    assert after == before
    assert f"--kit {WORKFLOW_KIT} codex {project}" in assert_sandbox_called(calls_log)


def test_canonical_workflow_kit_owns_the_complete_service_skill() -> None:
    assert (WORKFLOW_KIT / "spec.yaml").read_text(encoding="utf-8") == (
        'schemaVersion: "1"\nkind: mixin\nname: specode-loop-workflow-skills\n'
    )
    skill_manifest = (WORKFLOW_SKILL / "SKILL.md").read_text(encoding="utf-8")
    policy = (WORKFLOW_SKILL / "agents" / "openai.yaml").read_text(
        encoding="utf-8"
    )
    assert "name: specode-loop-implement" in skill_manifest
    assert "allow_implicit_invocation: true" in policy
    assert not (
        ROOT_DIR / ".agents" / "skills" / "do-work" / "SKILL.md"
    ).exists()
    assert not (
        ROOT_DIR / ".agents" / "skills" / "specode-do-work" / "SKILL.md"
    ).exists()


def test_host_global_do_work_skill_is_ignored(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path, "with-global-do-work")
    codex_home = make_global_do_work_skill(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, path=path, codex_home=codex_home)

    assert result.returncode == 0
    assert not (project / ".agents").exists()
    assert "workflow skill synced" not in result.stdout.lower()
    assert f"--kit {WORKFLOW_KIT} codex {project}" in assert_sandbox_called(calls_log)


def test_missing_canonical_workflow_kit_fails_before_sandbox_execution(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path)
    path, calls_log = install_fake_sbx(tmp_path)
    monkeypatch.setenv("FAKE_SBX_CALLS", str(calls_log))
    isolated_runner = tmp_path / "isolated-runner" / "scripts" / "specode_loop.py"
    isolated_runner.parent.mkdir(parents=True)
    shutil.copyfile(RUNNER, isolated_runner)
    shutil.copyfile(
        ITERATION_MODULE, isolated_runner.with_name("specode_loop_iteration.py")
    )

    result = run_loop(project, path=path, runner=isolated_runner)

    assert result.returncode == 1
    assert "Error: invalid Workflow Kit: required directory is missing:" in result.stderr
    assert "isolated-runner/sandbox-kits/workflow-skills" in result.stderr
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


def test_missing_host_skill_does_not_trigger_target_project_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    project = make_project(tmp_path)
    path, calls_log, _rm_log = prepare_fake_runtime(tmp_path, monkeypatch)
    write_scenario(tmp_path, 1, "ALL TASKS DONE\n")

    result = run_loop(project, path=path, codex_home=tmp_path / "missing-codex-home")

    assert result.returncode == 0
    assert not (project / ".agents").exists()
    assert "workflow skill synced" not in result.stdout.lower()
    calls = assert_sandbox_called(calls_log)
    assert f"--kit {WORKFLOW_KIT} codex {project}" in calls


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
        (("--auth",), "--auth requires a value"),
        (("--auth", "automatic"), "--auth must be one of: oauth, api-key"),
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
    imports_by_module: dict[Path, set[str]] = {}
    for runtime_module in (RUNNER, ITERATION_MODULE):
        tree = ast.parse(runtime_module.read_text(encoding="utf-8"))
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
        imports_by_module[runtime_module] = runtime_imports

    assert imports_by_module[RUNNER] <= set(sys.stdlib_module_names) | {
        "specode_loop_iteration"
    }
    assert imports_by_module[ITERATION_MODULE] <= set(sys.stdlib_module_names)
    assert "specode_loop_iteration" in imports_by_module[RUNNER]
    assert "specode_loop" not in imports_by_module[ITERATION_MODULE]
