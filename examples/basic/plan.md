# Plan: Specode Loop Example Acceptance Fixture

> Source PRD: prd.md

## Architectural decisions

Durable decisions that apply across all phases:

- **Planning documents**: The Target Project uses conventional root-level
  `prd.md` and `plan.md` files.
- **Execution boundary**: Each unchecked phase is completed by one Sandbox
  Iteration.
- **Verification seam**: The final behavior is verified through an executable
  shell command rather than implementation details.
- **Determinism**: All expected outputs are exact plain text strings.
- **Runner-managed configuration**: `.agents/skills/specode-do-work` remains
  owned by Specode Loop and is not modified by task work.

---

## [ ] Phase 1: Artifact Status Trail

**User stories**: 2, 3, 5, 6

### What to build

Create the first visible project artifact and then extend it in a later Sandbox
Iteration. This phase proves that Specode Loop can complete dependent file work
one phase at a time.

### Acceptance criteria

- Create `artifact.txt` containing exactly `Specode Loop example task 1 complete.`
- Append `Specode Loop example task 2 complete.` on a new line in `artifact.txt`.

## Blocked by

None - can start immediately

---

## [ ] Phase 2: Derived Summary

**User stories**: 1, 2, 3, 5, 6

### What to build

Add a summary derived from the artifact trail. This phase proves that a later
Sandbox Iteration can read prior work and create a second deterministic project
artifact from it.

### Acceptance criteria

- Create `summary.md` containing exactly:
  ```markdown
  # Specode Loop Example Summary

  - Task 1: Specode Loop example task 1 complete.
  - Task 2: Specode Loop example task 2 complete.
  ```

## Blocked by

- Blocked by #1: Artifact Status Trail

---

## [ ] Phase 3: Executable Verification

**User stories**: 1, 3, 4, 5, 6

### What to build

Add a command that verifies the finished Target Project from the outside. This
phase proves that the final e2e state can be checked through behavior after all
Sandbox Iterations finish.

### Acceptance criteria

- Create executable `verify.sh` that exits with status 0 only when `artifact.txt` and `summary.md` match the expected contents, and prints exactly `Specode Loop example verified.` on success.

## Blocked by

- Blocked by #1: Artifact Status Trail
- Blocked by #2: Derived Summary
