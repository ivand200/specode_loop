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
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['FAKE_SBX_CALLS']).open('a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "if args[0] == 'create':\n"
        "    print('sandbox created')\n"
        "elif args[0] == 'exec':\n"
        "    print('streamed Codex progress')\n"
        "    output_path = Path(args[args.index('-o') + 1])\n"
        "    output_path.write_text('ALL TASKS DONE\\n', encoding='utf-8')\n"
        "elif args[0] != 'rm':\n"
        "    raise SystemExit(127)\n",
        encoding="utf-8",
    )
    fake_sbx.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", calls_log


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
        json.loads(line)
        for line in calls_log.read_text(encoding="utf-8").splitlines()
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
    assert "If no undone AFK Plan Tasks remain, output exactly:\nALL TASKS DONE" in prompt
    assert remove == ["rm", "--force", sandbox_name]
    assert not list(tmp_path.glob("specode_loop.*"))
    assert not list(project.glob(".specode_loop-last-message.*"))
