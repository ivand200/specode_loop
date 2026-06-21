# Store Bundled Skills Under `.agents/skills`

Specode Loop will store its bundled workflow skills in its own repository under `.agents/skills/specode-*`. The runner will sync the Specode-owned skill directories it needs into the target project's `.agents/skills/` tree, avoiding per-skill environment variables and keeping future bundled skills on the same native Codex skill path.
