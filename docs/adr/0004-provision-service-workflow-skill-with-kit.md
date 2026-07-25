# Provision the Service Implementation Skill with a Workflow Kit

Specode Loop will deliver its `specode-loop-implement` Service Implementation
Skill through the checked-in Docker Sandbox mixin at
`sandbox-kits/workflow-skills`. The complete skill directory inside the kit is
the sole service-owned source of truth. The minimal kit manifest declares only
schema version `1`, kind `mixin`, and the name
`specode-loop-workflow-skills`; static home-file injection uses the kit's
conventional `files/home/` layout.

The user-facing runner resolves this canonical kit only relative to its own
repository root. Before project-log initialization or sandbox creation, it
checks the required kit files, requires Docker Sandbox 0.37.0 or newer, probes
the real `sbx create --no-share-skills --help` parser, and invokes
`sbx kit validate`. Successful preflight yields one absolute resolved kit
directory and the evidence line `Workflow kit validated: <path>`.

Every Sandbox Iteration receives that validated directory through its frozen
request and privately adds `--no-share-skills` and `--kit <path>` to sandbox
creation. Docker's global shared-skill store is disabled, while Target Project
skills remain visible. Provisioning never creates, replaces, restores, or
deletes Target Project `.agents` content.

The sandbox prompt explicitly requests `$specode-loop-implement`. An ordinary
Target Project `$do-work` skill is unrelated and remains available. If the
Target Project deliberately declares a same-named `specode-loop-implement`
skill, normal project-level Codex precedence applies; Specode Loop does not
scan for, reject, hide, or rank project skills.
