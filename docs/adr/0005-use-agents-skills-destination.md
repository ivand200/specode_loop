# Use `.agents/skills` for Bundled Skills

Specode Loop will copy bundled workflow skills into the target project's `.agents/skills/<skill-name>` directory before launching Docker Sandbox. This matches Codex CLI's documented repository skill discovery path, so the sandboxed `codex exec` run can treat the copied workflow as a native project skill instead of merely reading an arbitrary Markdown file.
