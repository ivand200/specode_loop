from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
HARNESS = ROOT_DIR / "tests" / "specode_loop_workflow_kit-e2e.sh"


def test_workflow_kit_e2e_harness_exercises_both_cases_with_fake_sbx(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state_file = tmp_path / "fake-sbx-state"
    fake_sbx = bin_dir / "sbx"
    fake_sbx.write_text(
        """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
state_path = pathlib.Path(os.environ["FAKE_SBX_STATE"])
state = json.loads(state_path.read_text()) if state_path.exists() else {}

if args == ["version"]:
    print("sbx version: v0.37.0 test-build")
elif args[:3] == ["secret", "ls", "-g"]:
    print("openai oauth")
elif args == ["create", "--no-share-skills", "--help"]:
    pass
elif args[:2] == ["kit", "validate"]:
    pass
elif args and args[0] == "create":
    name = args[args.index("--name") + 1]
    state[name] = args[-1]
    state_path.write_text(json.dumps(state))
elif args and args[0] == "exec":
    name = args[1]
    final_message = pathlib.Path(args[args.index("-o") + 1])
    marker = (
        "SPECODE_LOOP_E2E_PROJECT_OVERRIDE_SELECTED"
        if state[name].endswith("project-override")
        else "SPECODE_LOOP_E2E_KIT_SKILL_SELECTED"
    )
    content = f"{marker}\\nALL TASKS DONE\\n"
    final_message.write_text(content)
    print(content, end="")
elif args[:2] == ["rm", "--force"]:
    state.pop(args[2], None)
    state_path.write_text(json.dumps(state))
elif args == ["ls", "--json"]:
    print(json.dumps([{"name": name} for name in state]))
else:
    print(f"unsupported fake sbx command: {args}", file=sys.stderr)
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    fake_sbx.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
            "FAKE_SBX_STATE": str(state_file),
            "TMPDIR": str(tmp_path),
        }
    )
    result = subprocess.run(
        ["bash", str(HARNESS)],
        cwd=ROOT_DIR,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Workflow Kit E2E case passed: default" in result.stdout
    assert "Workflow Kit E2E case passed: override" in result.stdout
    assert "Specode Loop Workflow Kit real E2E passed." in result.stdout
    assert json_state(state_file) == {}


def json_state(state_file: Path) -> dict[str, str]:
    import json

    return json.loads(state_file.read_text(encoding="utf-8"))
