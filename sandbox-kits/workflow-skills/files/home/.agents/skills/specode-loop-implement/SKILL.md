---
name: specode-loop-implement
description: "Execute one Specode Loop Plan Task end-to-end: plan, implement, validate with typecheck and tests. Use for a Specode Loop Sandbox Iteration."
---

# Specode Loop Implement

Execute **ONE** complete unit of work: plan it, build it, validate it, commit it.
Take the first eligible undone AFK Plan Task and implement it.

## Workflow

### 1. Understand the task

Read any referenced plan or PRD. Explore the codebase to understand the relevant files, patterns, and conventions. If the task is ambiguous, ask the user to clarify scope before proceeding.

### 2. Plan the implementation (optional)

If the task has not already been planned, create a plan for it.

### 3. Implement

**For backend code**: use red/green/refactor, one test at a time in a tracer-bullet style. Use `/tdd` skill where possible, at pre-agreed seams.
Core principle: Tests should verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't.

Each test should target one thin vertical slice through the system. Do not write all tests upfront — write one, make it pass, then move to the next.

**For frontend code**: implement directly without TDD.

### 4. Validate

Run the feedback loops and fix any issues. Repeat until all pass cleanly.

Run typecheckers, linters and tests.

Mark only that Plan Task and its acceptance criteria complete when all tests pass.
