---
name: specode-do-work
description: "Specode Loop runner workflow for completing exactly one planned task in a sandbox iteration."
---

# Specode Do Work

Execute one Specode Loop task end-to-end inside the sandbox.

## Workflow

### 1. Understand the task

Read the PRD document and plan document named by the runner prompt. Follow the runner prompt's task-selection rules exactly, including any AFK/HITL boundaries, and select exactly one eligible undone plan task.

If there are no eligible undone plan tasks, output exactly:

```text
ALL TASKS DONE
```

Do no task work in that case.

### 2. Implement

Complete only the selected task. Work directly in the project working tree.

Do not modify runner-managed copied workflow skill files under `.agents/skills/specode-do-work` as part of task work.

Do not make a git commit unless the PRD document or plan document explicitly requires it.

### 3. Validate

Run the relevant feedback loops for the task, such as tests, linters, typecheckers, or direct command checks. Fix issues until the selected task is genuinely complete.

### 4. Update the plan and report

Mark the completed task done in the plan document by changing its checkbox from `[ ]` to `[x]`.

When the selected task is complete and the plan document has been updated, output exactly:

```text
TASK DONE
```

Do not output `TASK DONE` unless the selected task is complete and the plan document was updated.
