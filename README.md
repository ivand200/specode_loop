# Specode Loop

Specode Loop runs Codex inside Docker Sandbox against a Target Project one plan
task at a time.

A Target Project needs two Planning Documents:

- a PRD document describing the requested behavior
- a plan document with ordered Markdown checkbox Plan Tasks

By default those files are `prd.md` and `plan.md`. Use `--prd` and `--plan`
when a project uses different filenames.

During each sandbox iteration, Codex must finish exactly one eligible undone AFK
Plan Task, mark only that Plan Task complete, and print one success sentinel:

- `TASK DONE`
- `ALL TASKS DONE`

## Requirements

- Python 3.11+
- `uv`
- Docker Sandbox CLI (`sbx`) 0.37.0 or newer
- Codex auth available to Docker Sandbox

Check the sandbox CLI:

```bash
command -v sbx
```

Specode Loop uses ChatGPT/Codex OAuth by default. Configure Docker Sandbox
OAuth on the host before running the loop:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
sbx secret set -g openai --oauth
sbx secret ls -g --service openai
```

The runner verifies the stored global OpenAI credential before creating a
sandbox. In the default OAuth mode it refuses a stored API key and removes
`OPENAI_API_KEY` and `CODEX_API_KEY` from every `sbx` subprocess environment,
preventing an inherited key from silently selecting API-key billing.

For deliberate API-key billing, configure Docker's OpenAI secret and opt in on
the runner command:

```bash
sbx secret set -g openai
uv run python scripts/specode_loop.py "$DEMO_PROJECT" --auth api-key
```

Docker Sandbox stores either OAuth or an API key for the global `openai`
service; changing the stored credential affects newly created sandboxes.

### Sandbox templates

Docker Sandbox caches agent templates across sandbox creation and removal. List
the cached templates before troubleshooting an outdated Codex CLI or model
metadata warning:

```bash
sbx template ls
```

To refresh the Codex template, remove only its cached image by the ID shown in
that output:

```bash
sbx template rm IMAGE_ID
```

The next Specode Loop run pulls the current `codex-docker` template. Avoid
`sbx reset` for routine template refreshes because it removes all sandbox data,
not just the selected cached template.

### Sandbox network policy

Docker Sandbox applies persistent host-side network policy to its sandboxes. A
new non-interactive installation can start with the recommended balanced
preset:

```bash
sbx policy init balanced
```

Inspect active rules, test a destination, and review blocked requests with:

```bash
sbx policy ls --wide
sbx policy check network api.openai.com
sbx policy log
```

Add a global allow rule for a required domain, or deliberately allow every
supported outbound HTTP/HTTPS destination:

```bash
sbx policy allow network api.example.com
sbx policy allow network "**"
```

Use `--sandbox NAME` to scope an allow rule to one existing named sandbox.
Organization-managed governance overrides local rules. Even an `"**"` rule
does not expose the host network, localhost, private IP ranges, or raw
TCP/UDP/ICMP traffic.

## Quick Start

Run the bundled example in a disposable directory:

```bash
DEMO_PROJECT="$(mktemp -d "${TMPDIR:-/tmp}/specode-loop-demo.XXXXXX")"
cp -R examples/basic/. "$DEMO_PROJECT"
uv run python scripts/specode_loop.py "$DEMO_PROJECT"
```

Override model or reasoning effort when needed:

```bash
uv run python scripts/specode_loop.py "$DEMO_PROJECT" \
  --model YOUR_CODEX_MODEL \
  --reasoning-effort medium
```

Verbose transcript logging:

```bash
SPECODE_LOOP_VERBOSE=1 uv run python scripts/specode_loop.py "$DEMO_PROJECT"
```

## Usage

```bash
uv run python scripts/specode_loop.py PROJECT_DIR [options]
```

Options:

| Option | Default | Purpose |
| --- | --- | --- |
| `--prd PATH` | `prd.md` | PRD document path inside the Target Project |
| `--plan PATH` | `plan.md` | Plan document path inside the Target Project |
| `--max-iterations N` | `12` | Maximum sandbox iterations |
| `--auth MODE` | `oauth` | OpenAI auth mode: `oauth` or explicit `api-key` opt-in |
| `--model MODEL` | `gpt-5.6-sol` | Codex model passed to `codex exec -m` |
| `--effort EFFORT` | `medium` | Reasoning effort: `minimal`, `low`, `medium`, `high`, `xhigh` |
| `--reasoning-effort EFFORT` | `medium` | Alias for `--effort` |

Custom Planning Document paths are resolved inside `PROJECT_DIR`:

```bash
uv run python scripts/specode_loop.py /path/to/project \
  --prd docs/product-requirements.md \
  --plan planning/implementation-plan.md
```

Absolute `--prd` and `--plan` paths are accepted only when they resolve inside
the Target Project.

## Workflow Kit

Specode Loop ships its Service Implementation Skill in the checked-in Docker
Sandbox mixin at `sandbox-kits/workflow-skills`. The complete
`specode-loop-implement` skill inside that kit is the service-owned source of
truth.

Before creating the project log or any sandbox, the runner validates the kit's
required files, requires Docker Sandbox 0.37.0 or newer, probes support for
`--no-share-skills`, and runs `sbx kit validate`. Successful preflight prints
and logs:

```text
Workflow kit validated: <absolute-resolved-kit-path>
```

Every Sandbox Iteration creates a Codex sandbox with the validated kit and
Docker's global shared-skill store disabled. Its prompt explicitly says:

```text
Use the `$specode-loop-implement` skill to execute this iteration.
```

Provisioning never creates, replaces, restores, or deletes `.agents` content
in the Target Project. Project skills remain visible, including an ordinary
project `$do-work` skill. If a Target Project deliberately defines its own
`specode-loop-implement` skill, normal project-level Codex precedence applies;
Specode Loop does not scan for or reject that declaration.

## Logs

Specode Loop writes `specode_loop.log` in the Target Project.

Default logs include the validated Workflow Kit, selected Planning Documents,
model and reasoning effort, iteration status, Success Sentinel detection, and
sandbox cleanup. Raw Codex transcripts are included only when
`SPECODE_LOOP_VERBOSE=1`.

## Tests

### Pull-request CI

Every pull request, including documentation-only, fork, and Dependabot pull
requests, runs the secretless `CI` workflow. It reports these checks:

- `Ruff quality` checks formatting and linting on Python 3.11.
- `Tests (Python 3.11)` and `Tests (Python 3.14)` run the complete deterministic
  test suite.
- `CI / required` is the stable merge signal. It succeeds only after Ruff and
  both Python test jobs succeed; a failure, timeout, or cancellation keeps it
  non-green.

Run the same locked checks locally:

```bash
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check --output-format=github .
uv run --locked pytest
```

GitHub Actions does not receive Docker Sandbox or OpenAI credentials and does
not execute real-request E2E harnesses.

### Manual release readiness

The secretless `Release readiness` workflow verifies a provisional candidate
without publishing it. In GitHub Actions, choose **Release readiness**, select
**Run workflow**, and enter the candidate branch, tag, or full commit SHA in
`candidate_ref`.

The workflow repeats locked Ruff checks and the complete deterministic test
suite on Python 3.11 and 3.14. If they pass, it creates one runtime-only archive
from the exact checked-out commit, extracts it into a fresh directory, verifies
its manifest, and starts the extracted CLI with:

```bash
uv run --locked --no-dev python scripts/specode_loop.py --help
```

A successful manual run retains `specode-loop-<short-commit>.tar.gz` under the
stable `release-readiness-archive` artifact label for 14 days. GitHub reports
the upload digest. The result is provisional: it does not publish a release,
sign or attest the archive, or deploy anything.

### Real E2E

Run the optional real E2E harness only when `sbx`, Docker Sandbox auth, network
access, and real Codex execution are available:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_python-e2e.sh
```

Run the focused two-project Workflow Kit E2E to verify real service-skill
discovery, deliberate project override precedence, Target Project invariance,
and sandbox removal:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_workflow_kit-e2e.sh
```

Run a focused one-request authentication E2E against the globally configured
Docker Sandbox OpenAI credential:

```bash
# OAuth (default)
bash tests/specode_loop_auth-e2e.sh

# Deliberate API-key mode
SPECODE_LOOP_AUTH_E2E_MODE=api-key \
  bash tests/specode_loop_auth-e2e.sh
```

## More Detail

Architecture decisions live in `docs/adr/`. Root-level local planning files,
logs, secrets, `.codex/`, generated fixtures, and `/tasks` are intentionally
kept out of version control for local development.
