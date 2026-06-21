# Define Required Skills in the Runner

Specode Loop will keep an internal `SPECODE_REQUIRED_SKILLS` list in `scripts/specode_loop.sh`, starting with `specode-do-work`. The runner syncs only those required Specode-owned skill directories from its bundled `.agents/skills/` tree into the target project's `.agents/skills/`, avoiding user-facing skill flags and avoiding unused bundled skills in target projects.
