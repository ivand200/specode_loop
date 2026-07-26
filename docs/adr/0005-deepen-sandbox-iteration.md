# Deepen the Sandbox Iteration

Specode Loop will represent one complete Sandbox Iteration with a deep internal
module. Previously, the user-facing runner constructed commands, managed
attempt-scoped files and sandbox identity, classified Success Sentinels, and
coordinated cleanup through mutable loop state. That spread one cohesive
operation across the caller and callee, made ordering implicit, and allowed a
Sandbox Iteration to return while resources still required caller-managed
cleanup.

The user-facing `scripts/specode_loop.py` remains responsible for command
parsing, Planning Document and Target Project preflight, authentication,
Workflow Kit validation, project-log initialization, process-wide signal
policy, cross-iteration continuation, the maximum-iteration policy, and final
process status. Its only Sandbox Iteration dependency is the sibling
`scripts/specode_loop_iteration.py` module, imported in one direction. The
iteration module never imports the runner.

The iteration module exposes exactly three public names:
`SandboxIterationRequest`, `SandboxIterationOutcome`, and
`run_sandbox_iteration`. The frozen request carries already-validated values,
including the accepted absolute Workflow Kit path, without exposing Docker
command options. One function call creates and executes at most one sandboxed
Codex attempt and
returns one exhaustive outcome: one Plan Task completed, all Plan Tasks
completed, or failure. The runner matches those outcomes explicitly and does
not inspect command status, Success Sentinel evidence, sandbox identity,
artifacts, or cleanup state.

Sandbox Iteration owns prompt and command construction, streamed output,
final-message capture, Success Sentinel classification, diagnostics,
iteration reporting, the active direct `sbx` child, temporary artifacts,
sandbox identity, and forced sandbox removal. It returns or propagates an
unexpected condition only after all attempt-scoped cleanup stages have been
attempted. Active child unwinding precedes artifact deletion, and artifact
deletion precedes forced sandbox removal. Cleanup remains best effort, runs
each target at most once without retries, and never replaces the classified
outcome or original exception.

Production and deterministic tests substitute Docker Sandbox at the same
operating-system executable seam: production resolves the real `sbx`, while
tests place a scenario-controlled fake executable on `PATH`. Direct tests call
`run_sandbox_iteration` for classification, command, reporting, lifecycle, and
request-precondition behavior. Runner tests use the executable interface for
CLI and preflight compatibility, request mapping, cross-iteration policy,
status mapping, and representative interruption composition. Both runtime
modules use only the Python standard library; the runner-to-iteration import
is the single local runtime edge.

The two sibling runtime files are intentional. A package hierarchy or shared
utilities module would add navigation and broaden the seam without a second
implementation or caller. A reusable lifecycle object was rejected because it
would introduce identity and idle/running invariants that no caller needs. A
reporter interface, callback protocol, or event stream was rejected because it
would expose internal phase ordering and cleanup choreography. A Python
subprocess adapter was rejected because the executable seam already serves
production and tests. Dual execution, feature flags, background work, process
tree management, and automatic retries were rejected because they could
duplicate work or expand ownership beyond one synchronous Sandbox Iteration.
