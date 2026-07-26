# Keep Specode Loop Narrow

Specode Loop will remain a narrow Python runner instead of becoming a general orchestration framework.

The runner owns a small command surface, performs local preflight checks, validates one checked-in Workflow Kit, invokes Docker Sandbox directly, and watches for exact Success Sentinels. Broader orchestration concerns such as durable multi-run state, remote job management, tool installation policy, credential brokering, and network policy belong outside this project until a concrete Specode Loop use case requires them.
