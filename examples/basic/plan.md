# Tickets: Specode Loop Request Response Fixture

Build a deterministic local request/response flow that exercises repeated
Sandbox Iterations through one external verification seam.

> Source PRD: prd.md

Work the **frontier**: any AFK ticket whose blockers are all done. Complete
exactly one frontier ticket per Sandbox Iteration.

## [ ] 1. Seed Request Artifact

**Type:** AFK

**What to build:** Create the first visible project artifact: a deterministic
local request that later tickets can answer and verify.

**Blocked by:** None — can start immediately.

- [ ] Create `request.txt` containing exactly:
  ```text
  REQUEST_ID: specode-basic-001
  USER_REQUEST: Summarize the Specode Loop demo state.
  EXPECTED_RESPONSE_KIND: deterministic-summary
  ```
- [ ] Do not create the response, transcript, or verification command in this
  ticket.

## [ ] 2. Deterministic Response Artifact

**Type:** AFK

**What to build:** Read the seeded request and create the deterministic response
artifact, proving that a later Sandbox Iteration can use prior Target Project
state.

**Blocked by:** Seed Request Artifact.

- [ ] Confirm `request.txt` exists and contains the expected request identifier.
- [ ] Create `response.txt` containing exactly:
  ```text
  RESPONSE_ID: specode-basic-001
  STATUS: complete
  SUMMARY: Specode Loop can turn one local request into one deterministic response.
  ```
- [ ] Do not create the transcript or verification command in this ticket.

## [ ] 3. Reviewable Transcript

**Type:** AFK

**What to build:** Pair the request with its response in a short,
human-reviewable transcript derived from the earlier artifacts.

**Blocked by:** Seed Request Artifact; Deterministic Response Artifact.

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
- [ ] Do not create the verification command in this ticket.

## [ ] 4. QA Notes and Executable Integration Check

Populate this ticket only after the implementation tickets are complete.

**Type:** AFK

**What to build:** Add the external verification seam and record the critical
review points for the finished Target Project.

**Blocked by:** All the tickets above.

- [ ] Create executable `verify.sh`.
- [ ] `./verify.sh` exits with status 0 only when `request.txt`, `response.txt`,
  and `transcript.md` match their expected contents.
- [ ] `./verify.sh` prints exactly
  `Specode Loop request/response example verified.` on success.
- [ ] **Most important, critical code parts for human review:** the exact
  request/response contract and `verify.sh` failure behavior.
- [ ] **Most critical test for human review:** run `./verify.sh` from the Target
  Project root and confirm its exact success output.
- [ ] **Most important user story for final manual QA:** one local request is
  carried across Sandbox Iterations into one deterministic, reviewable response.
- [ ] Leave all pre-existing Target Project `.agents` content unchanged.
