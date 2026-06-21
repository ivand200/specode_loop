---
name: specode-do-work
description: "Specode Loop runner workflow for completing exactly one planned task in a sandbox iteration."
---

# Specode Do Work

Execute one Specode Loop task end-to-end inside the sandbox.

## Workflow

### 1. Understand the task

Read `prd.md` and `plan.md` in the project root. Select exactly the first undone Markdown checkbox task in `plan.md`, unless the plan gives explicit priority rules.

If there are no undone checkbox tasks, output exactly:

```text
ALL TASKS DONE
```

Do no task work in that case.

### 2. Implement

Complete only the selected task. Work directly in the project working tree.

Do not modify runner-managed copied workflow skill files under `.agents/skills/specode-do-work` as part of task work.

Do not make a git commit unless `prd.md` or `plan.md` explicitly requires it.

### 3. Validate

Run the relevant feedback loops for the task, such as tests, linters, typecheckers, or direct command checks. Fix issues until the selected task is genuinely complete.

### 4. Update the plan and report

Mark the completed task done in `plan.md` by changing its checkbox from `[ ]` to `[x]`.

When the selected task is complete and `plan.md` has been updated, output exactly:

```text
TASK DONE
```

Do not output `TASK DONE` unless the selected task is complete and `plan.md` was updated.
