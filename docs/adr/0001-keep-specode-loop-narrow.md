# Keep Specode Loop Narrow

Specode Loop will remain a narrow shell runner rather than becoming a Sandcastle-style orchestration framework. Ralph and Sandcastle are useful references for hardening ideas such as durable progress, clear lifecycle boundaries, timeouts, and logging, but Specode Loop should preserve its current small command surface, direct Docker Sandbox execution boundary, and agent-owned plan task workflow.
