# Use the Bundled Skill by Default

Specode Loop will use the repository's bundled workflow skills and will not silently fall back to `$CODEX_HOME/skills/do-work`. Default behavior should be clone-and-run deterministic rather than shaped by hidden user-level Codex state, and v1 will not add per-skill environment overrides.
