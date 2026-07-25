from __future__ import annotations

import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RUNNER = ROOT_DIR / "scripts" / "specode_loop.py"
ITERATION_MODULE = ROOT_DIR / "scripts" / "specode_loop_iteration.py"
WORKFLOW_KIT = ROOT_DIR / "sandbox-kits" / "workflow-skills"
WORKFLOW_KIT_E2E = ROOT_DIR / "tests" / "specode_loop_workflow_kit-e2e.sh"
WORKFLOW_SKILL = (
    WORKFLOW_KIT
    / "files"
    / "home"
    / ".agents"
    / "skills"
    / "specode-loop-implement"
)


def tracked_paths() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT_DIR,
        check=True,
        stdout=subprocess.PIPE,
    )
    return tuple(
        ROOT_DIR / path.decode("utf-8")
        for path in result.stdout.split(b"\0")
        if path
    )


def release_text() -> str:
    release_paths = [
        ROOT_DIR / "README.md",
        ROOT_DIR / "CONTEXT.md",
        *sorted((ROOT_DIR / "docs" / "adr").glob("*.md")),
        *sorted((ROOT_DIR / "examples").rglob("*.md")),
        *sorted((ROOT_DIR / "scripts").glob("*.py")),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in release_paths)


def test_tracked_tree_has_one_service_workflow_skill_source() -> None:
    tracked = {
        path.relative_to(ROOT_DIR).as_posix()
        for path in tracked_paths()
    }

    canonical_skill = (
        "sandbox-kits/workflow-skills/files/home/.agents/skills/"
        "specode-loop-implement/SKILL.md"
    )
    service_sources = {
        path
        for path in tracked
        if path.endswith("/specode-loop-implement/SKILL.md")
        and not path.startswith("tests/fixtures/")
    }

    assert canonical_skill in tracked
    assert service_sources == {canonical_skill}
    assert not any(path.startswith(".agents/skills/") for path in tracked)
    assert not any("specode-do-work" in path for path in tracked)


def test_release_surface_rejects_legacy_skill_provisioning_vocabulary() -> None:
    text = release_text()
    forbidden = (
        "RUNNER_SKILLS_REL",
        "HOST_SKILLS_REL",
        "PREFERRED_WORKFLOW_SKILL",
        "FALLBACK_WORKFLOW_SKILL",
        "SPECODE_REQUIRED_SKILLS",
        "copy_skill_directory",
        "sync_preferred_global_skill",
        "sync_required_bundled_skills",
        "Global workflow skill synced:",
        "Bundled workflow skill synced:",
        ".agents/skills/specode-do-work",
        "$CODEX_HOME/skills/do-work",
        "~/.codex/skills/do-work",
        "bundled workflow skill",
        "falls back to",
        "explicitly invokes `$do-work`",
    )

    assert [term for term in forbidden if term in text] == []


def test_release_surface_contains_complete_workflow_kit_contract() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    iteration = ITERATION_MODULE.read_text(encoding="utf-8")
    manifest = (WORKFLOW_KIT / "spec.yaml").read_text(encoding="utf-8")
    skill = (WORKFLOW_SKILL / "SKILL.md").read_text(encoding="utf-8")
    policy = (WORKFLOW_SKILL / "agents" / "openai.yaml").read_text(
        encoding="utf-8"
    )

    assert manifest == (
        'schemaVersion: "1"\n'
        "kind: mixin\n"
        "name: specode-loop-workflow-skills\n"
    )
    assert "name: specode-loop-implement" in skill
    assert policy == "policy:\n  allow_implicit_invocation: true\n"
    assert "Workflow kit validated: {workflow_kit}" in runner
    assert "workflow_kit=workflow_kit" in runner
    assert "workflow_kit: _Path" in iteration
    assert '"--no-share-skills"' in iteration
    assert '"--kit"' in iteration
    assert (
        "Use the `$specode-loop-implement` skill to execute this iteration."
        in iteration
    )


def test_real_workflow_kit_e2e_covers_selection_invariance_and_cleanup() -> None:
    harness = WORKFLOW_KIT_E2E.read_text(encoding="utf-8")

    assert "SPECODE_LOOP_E2E_KIT_SKILL_SELECTED" in harness
    assert "SPECODE_LOOP_E2E_PROJECT_DO_WORK_SELECTED" in harness
    assert "SPECODE_LOOP_E2E_PROJECT_OVERRIDE_SELECTED" in harness
    assert "SPECODE_LOOP_VERBOSE=1" in harness
    assert "write_project_manifest" in harness
    assert "sha256" in harness
    assert "sbx ls --json" in harness
    assert ".specode_loop-last-message.*" in harness
    assert "Target Project changed beyond specode_loop.log" in harness
