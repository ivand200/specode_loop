# Treat Planning Documents as Roles

Specode Loop will treat the PRD and plan as Planning Document roles with conventional default filenames, not as fixed filenames.

By default the runner selects `prd.md` for the PRD role and `plan.md` for the plan role. Callers can override those paths with `--prd` and `--plan`. Relative Planning Document paths resolve from the target project, and absolute paths are accepted only when their resolved location is inside the target project.

The runner resolves paths before validation, so symlinks that escape the target project are rejected during preflight. The sandbox prompt names both document roles and their selected project-relative paths so the sandboxed Codex run reads the requested PRD document and updates the requested plan document.
