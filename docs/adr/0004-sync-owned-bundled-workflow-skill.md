# Sync the Owned Bundled Workflow Skill

Specode Loop will ship the runner-managed workflow skill in this repository and sync only the required Specode-owned skill directories into the target project before sandbox execution.

The bundled workflow skill is named `specode-do-work` and lives under `.agents/skills/specode-do-work` in this repository. Before each sandbox run, the Python runner copies that skill to `PROJECT_DIR/.agents/skills/specode-do-work` so Docker Sandbox can discover it through the native project-level Codex skill path without depending on host user-level Codex state.

The runner keeps the required bundled skills in an internal list in `scripts/specode_loop.py`, starting with `specode-do-work`. It does not expose per-skill flags, does not fall back to `$CODEX_HOME/skills`, and does not sync unused bundled skills.

During sync, Specode Loop may overwrite only its owned destination directory, `PROJECT_DIR/.agents/skills/specode-do-work`. It must leave all other target-project `.agents` files and skill directories untouched so the target project can maintain its own repo-level agent configuration alongside the runner-managed workflow skill.
