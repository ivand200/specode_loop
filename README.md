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

#### Protected `main` merge contract

One active repository ruleset targets only `main`. Changes must arrive through
a pull request with a successful, current `CI / required` result. If `main`
changes after a pull request is checked, update the branch and wait for the
required check to pass again before merging. Pending, failed, cancelled, or
stale results block the merge.

The ruleset blocks direct pushes, force pushes, and deletion of `main`. It
requires zero approving reviews so the solo maintainer can merge their own
green pull request, but it grants no routine bypass to administrators or any
other actor. Signed commits, linear history, code-owner review, conversation
resolution, merge queue, and deployment requirements are intentionally outside
this repository's merge contract.

If a workflow defect prevents `CI / required` from being created, an
administrator may deliberately disable or edit the ruleset only long enough to
repair the broken merge gate. Record the reason, keep the repair minimal, then
restore the ruleset and repeat the acceptance checks: a follow-up pull request
must require a current green `CI / required` result, and direct pushes, force
pushes, and deletion of `main` must be rejected. This emergency procedure is not
a configured bypass or a normal merge path.

### Dependency maintenance

Dependabot checks the repository root weekly for GitHub Actions and `uv`
development-tool updates. Minor and patch updates are grouped within each
ecosystem, major updates remain separate, and routine version-update pull
requests are capped at three per ecosystem. The Python 3.14 matrix entry is not
managed by Dependabot; advancing the newest-supported Python version requires a
deliberate maintenance pull request.

Dependabot pull requests follow the same secretless `pull_request` workflow as
all other contributions. They receive `Ruff quality`, both Python test jobs,
and `CI / required`, with no credential-bearing or write-capable workflow and
no auto-merge or branch-protection bypass.

Before merging an update:

- For an Action update, verify that every changed `uses:` reference remains a
  full commit SHA with its release version in the same-line comment. Review the
  release notes for permission, runtime, and workflow-syntax changes.
- For a `uv` update, verify that the declared development dependencies and
  `uv.lock` changed together as expected, then require the locked local checks
  above and the protected CI result to pass.
- Review major updates independently and merge only after human review; never
  enable auto-merge for routine or security proposals.

Repository administrators must also enable **Dependabot alerts** and
**Dependabot security updates** under **Settings > Advanced Security**. Security
fixes are then proposed promptly instead of waiting for the weekly version
update schedule, but still require normal CI and human review.

### Release readiness

The secretless `Release readiness` workflow verifies candidates without
publishing them. For a provisional manual check, choose **Release readiness**
in GitHub Actions, select **Run workflow**, and enter any candidate branch, tag,
or full commit SHA in `candidate_ref`.

The workflow repeats locked Ruff checks and the complete deterministic test
suite on Python 3.11 and 3.14. If they pass, it creates one runtime-only archive
from the exact checked-out commit, extracts it into a fresh directory, verifies
its manifest, and starts the extracted CLI with:

```bash
uv run --locked --no-dev python scripts/specode_loop.py --help
```

A successful manual run retains `specode-loop-<short-commit>.tar.gz` under the
stable `release-readiness-archive` artifact label for 14 days. GitHub reports
the upload digest. The result is provisional regardless of the selected ref.

Pushing a tag whose name starts with `v` also starts the workflow. Before
building, the workflow fetches the repository history and proves that the
tagged commit is reachable from `origin/main`. A qualifying tag run retains
`specode-loop-<tag>.tar.gz` under the same artifact label. A `v*` tag outside
`main` fails before archive construction, and tags that do not start with `v`
do not trigger this workflow.

Both manual and tag artifacts are retained for review only. The workflow does
not publish a release, compare the tag with the static project version, sign or
attest the archive, or deploy anything.

### Real E2E

Real Docker Sandbox/Codex E2E is a trusted local-machine activity. It is not
part of deterministic pull-request CI or the credential-free release-readiness
workflow, and GitHub never receives its credentials, paid requests, temporary
Target Projects, logs, or receipts.

#### Exploratory local runs

Developers may run any individual harness from any branch or working tree when
`sbx`, Docker Sandbox authentication, network access, and real Codex execution
are available. These runs provide exploratory feedback; they do not qualify a
commit for a release tag.

Run the focused one-request authentication harness against Docker Sandbox's
globally configured OpenAI credential:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_auth-e2e.sh
```

Run the two-request Workflow Kit harness to verify real service-skill discovery,
deliberate project override precedence, Target Project invariance, and sandbox
removal:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_workflow_kit-e2e.sh
```

Run the complete example-project harness, which can use up to five requests:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_python-e2e.sh
```

OAuth is the default and the only mode accepted for release qualification.
Deliberate API-key coverage is optional when authentication behavior changes,
but it cannot replace the qualifying OAuth run:

```bash
SPECODE_LOOP_AUTH_E2E_MODE=api-key \
  bash tests/specode_loop_auth-e2e.sh
```

#### Release-qualifying local run

Before creating a version tag, qualify the exact commit intended for that tag.
Start from the repository root, check out the commit, and require a clean
working tree. Record the full SHA for the receipt and stop if `git status`
prints anything:

```bash
git switch --detach INTENDED_COMMIT
git status --short
git rev-parse HEAD
```

Run the credential-free contract first. Every command must pass against that
same clean commit:

```bash
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check --output-format=github .
uv run --locked pytest
```

Then verify the local prerequisites: `sbx` 0.37.0 or newer is operational,
Docker Sandbox networking can reach the required services, and the global
`openai` secret contains a working OAuth credential. Do not print or copy the
credential into the receipt.

```bash
sbx --version
sbx secret ls -g --service openai
sbx policy check network api.openai.com
```

Choose and record one model for all three harnesses. Remove inherited API-key
variables, explicitly select OAuth, and run the harnesses in cheapest-first
order:

```bash
export SPECODE_LOOP_AUTH_E2E_MODEL=gpt-5.6-sol
export SPECODE_LOOP_WORKFLOW_KIT_E2E_MODEL=gpt-5.6-sol
export SPECODE_LOOP_PYTHON_E2E_MODEL=gpt-5.6-sol
unset OPENAI_API_KEY CODEX_API_KEY
unset SPECODE_LOOP_AUTH_E2E_MODE SPECODE_LOOP_E2E_AUTH
unset SPECODE_LOOP_WORKFLOW_KIT_E2E_AUTH SPECODE_LOOP_PYTHON_E2E_AUTH
bash tests/specode_loop_auth-e2e.sh
bash tests/specode_loop_workflow_kit-e2e.sh
bash tests/specode_loop_python-e2e.sh
```

The complete qualifying run plans at most eight real requests: one for
authentication, two for the Workflow Kit cases, and up to five for the example
project. The harnesses fail fast and must not be wrapped in automatic retries.
Stop after any failure, classify it, and record the requests already used.

- A **product failure** is an incorrect exit, failed behavioral assertion,
  missing sentinel, incorrect project state, or incorrect cleanup while the
  prerequisites are healthy. Fix the product and restart qualification on the
  corrected clean commit.
- An **infrastructure failure** is unavailable `sbx` or Docker Sandbox,
  missing or expired OAuth, provider/network unavailability, or rate limiting
  before product behavior can be evaluated. After remediation, the operator
  may manually rerun only the failed harness.

Both failure classes block qualification. A targeted infrastructure rerun does
not erase the original result: record both attempts. All three harnesses must
ultimately pass with OAuth against the same clean commit before it is tagged.

#### Receipt and cleanup

Keep one minimal Markdown or text receipt under
`test_dir/real-e2e-evidence/` for 30 days. This directory is ignored and must
never be committed or uploaded. Record only:

- exact commit SHA and clean-working-tree confirmation;
- UTC start and end times;
- `sbx` version, selected model, and `oauth` mode;
- each command and pass/fail result;
- planned and used real-request counts; and
- any failure classification, remediation, and targeted-rerun result.

Never put OAuth material, API keys, raw transcripts, verbose logs, or temporary
Target Projects in routine evidence. A failed harness can leave a temporary
directory for diagnosis; delete the exact directory it reports after the issue
is understood. Remove any other diagnostic data before the receipt expires.
The tag-triggered release-readiness workflow separately verifies the
credential-free archive; GitHub does not ingest or validate this local receipt.

## More Detail

Architecture decisions live in `docs/adr/`. Root-level local planning files,
logs, secrets, `.codex/`, generated fixtures, `/tasks`, `/AGENTS.md`, and
`/test_dir` are intentionally kept out of version control for local
development.
