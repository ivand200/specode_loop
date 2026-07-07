# Specode Loop

Specode Loop is a runner for executing Codex against a project plan one task at a time inside Docker Sandbox. This context names the workflow concepts that matter to the runner and its users.

## Language

**Specode Loop**:
The automation runner that repeatedly asks Codex to complete one planned task inside a target project until the plan is finished or the loop stops.
_Avoid_: Runner, script, loop

**Target Project**:
The project directory that Specode Loop operates on. It contains the planning documents and receives the changes made by sandboxed Codex runs.
_Avoid_: Workspace, repo, fixture

**Planning Documents**:
The target project's selected PRD document and plan document, used together as the source of requested behavior and ordered work. By convention, the default filenames are `prd.md` and `plan.md`, but projects may choose different filenames through the runner command.
_Avoid_: Docs, specs

**Plan Task**:
An eligible undone AFK phase in the selected plan document that can be selected for a sandbox iteration.
_Avoid_: Step, item, todo, acceptance criterion

**Sandbox Iteration**:
One sandboxed Codex run that either completes exactly one plan task, reports that all plan tasks are complete, or fails without a success sentinel.
_Avoid_: Run, pass, cycle

**Success Sentinel**:
An exact output line from sandboxed Codex that tells Specode Loop whether one plan task was completed or no undone plan tasks remain.
_Avoid_: Marker, status, signal

**Work Protocol**:
The instructions sandboxed Codex follows when selecting, completing, and reporting exactly one plan task during a sandbox iteration.
_Avoid_: Skill, agent config, local setup

**Preferred Workflow Skill**:
The host global `do-work` skill that Specode Loop copies into a target project as `.agents/skills/do-work` when it exists, making it available to sandboxed Codex.
_Avoid_: Project-local skill, copied skill

**Bundled Fallback Workflow Skill**:
The versioned fallback workflow skill directory shipped at `.agents/skills/specode-do-work` and copied into a target project before sandbox execution for Docker Sandbox runs where a host global `do-work` skill is unavailable. Its `SKILL.md` is kept as an exact copy of the global `do-work` skill source of truth, so the directory is runner-managed as `specode-do-work` while the manifest currently declares `name: do-work`.
_Avoid_: Global skill, user skill, local skill
