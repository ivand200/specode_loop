# Copy Project-Level Agent Configuration

Specode Loop will make bundled workflow skills available to Docker Sandbox by copying them into the target project's project-level agent configuration before each `sbx run codex`. Docker Sandboxes do not load host user-level agent configuration, and Docker recommends collocating needed agent configuration with the project; Docker kits are deferred until Specode Loop needs runtime tool installation, credentials, network policy, or other kit-specific capabilities.
