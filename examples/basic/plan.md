# Plan: Specode Loop Request Response Fixture

> Source PRD: prd.md

## Architectural decisions

Durable decisions that apply across all phases:

- **Planning documents**: The Target Project uses conventional root-level
  `prd.md` and `plan.md` files.
- **Execution boundary**: Each unchecked AFK phase is completed by one Sandbox
  Iteration.
- **Request/response contract**: The example models one local request, one
  deterministic response, and one reviewable transcript.
- **Verification seam**: Final behavior is verified through an executable shell
  command rather than implementation details.
- **Determinism**: All expected outputs are exact plain text strings.
- **Runner-managed configuration**: `.agents/skills/specode-do-work` remains
  owned by Specode Loop and is not modified by task work.

---

## [ ] Phase 1: Seed Request Artifact

**Type**: AFK

**User stories**: 1, 2, 3, 4, 6, 7, 8

### What to build

Create the first visible project artifact: a deterministic local request that
later phases can answer and verify. This phase proves that the first Sandbox
Iteration can establish stable request context for the rest of the plan.

### Acceptance criteria

- [ ] Create `request.txt` containing exactly:
  ```text
  REQUEST_ID: specode-basic-001
  USER_REQUEST: Summarize the Specode Loop demo state.
  EXPECTED_RESPONSE_KIND: deterministic-summary
  ```
- [ ] Do not create the response, transcript, or verification command in this
  phase.

## Blocked by

None - can start immediately.

---

## [ ] Phase 2: Deterministic Response Artifact

**Type**: AFK

**User stories**: 2, 3, 4, 6, 7, 8

### What to build

Read the seeded request and create the deterministic response artifact. This
phase proves that a later Sandbox Iteration can use prior project state to
produce the next request/response output.

### Acceptance criteria

- [ ] Confirm `request.txt` exists and contains the expected request identifier.
- [ ] Create `response.txt` containing exactly:
  ```text
  RESPONSE_ID: specode-basic-001
  STATUS: complete
  SUMMARY: Specode Loop can turn one local request into one deterministic response.
  ```
- [ ] Do not create the transcript or verification command in this phase.

## Blocked by

- Blocked by #Phase 1: Seed Request Artifact

---

## [ ] Phase 3: Reviewable Transcript

**Type**: AFK

**User stories**: 2, 3, 4, 6, 7, 8

### What to build

Create a short transcript that pairs the request with its response in a
human-reviewable form. This phase proves that another Sandbox Iteration can
combine earlier artifacts into a derived output.

### Acceptance criteria

- [ ] Confirm `request.txt` and `response.txt` exist before creating the
  transcript.
- [ ] Create `transcript.md` containing exactly:
  ```markdown
  # Specode Loop Request/Response Transcript

  ## Request

  Summarize the Specode Loop demo state.

  ## Response

  Specode Loop can turn one local request into one deterministic response.
  ```
- [ ] Do not create the verification command in this phase.

## Blocked by

- Blocked by #Phase 1: Seed Request Artifact
- Blocked by #Phase 2: Deterministic Response Artifact

---

## [ ] Phase 4: Executable Integration Check

**Type**: AFK

**User stories**: 1, 2, 4, 5, 6, 7, 9, 10

### What to build

Add the external verification seam for the finished Target Project. This phase
proves that real e2e tests can validate completed behavior by running one command
instead of inspecting implementation choices.

### Acceptance criteria

- [ ] Create executable `verify.sh`.
- [ ] `./verify.sh` exits with status 0 only when `request.txt`, `response.txt`,
  and `transcript.md` match their expected contents.
- [ ] `./verify.sh` prints exactly
  `Specode Loop request/response example verified.` on success.
- [ ] Leave `.agents/skills/specode-do-work` unchanged.

## Blocked by

- Blocked by #Phase 1: Seed Request Artifact
- Blocked by #Phase 2: Deterministic Response Artifact
- Blocked by #Phase 3: Reviewable Transcript
