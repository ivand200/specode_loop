# Specode Loop

Specode Loop runs Codex inside Docker Sandbox one plan task at a time.

It expects a project directory with:

- `prd.md`
- `plan.md`
- Markdown checkbox tasks in `plan.md`

Each sandboxed Codex run must complete exactly the first undone checkbox task, mark only that task as done, and print one exact sentinel line:

- `TASK DONE`
- `ALL TASKS DONE`

## Quick Start

Create a disposable copy of the example target project:

```bash
DEMO_PROJECT="$(mktemp -d "${TMPDIR:-/tmp}/specode-loop-demo.XXXXXX")"
cp -R examples/basic/. "$DEMO_PROJECT"
scripts/specode_loop.sh "$DEMO_PROJECT"
```

Use a specific model or reasoning effort when you want to override your Codex defaults:

```bash
scripts/specode_loop.sh "$DEMO_PROJECT" --model YOUR_CODEX_MODEL --reasoning-effort medium
```

Verbose transcript logging:

```bash
SPECODE_LOOP_VERBOSE=1 scripts/specode_loop.sh "$DEMO_PROJECT"
```

The repository root is the source repo for Specode Loop. Target projects live in `examples/`, `tests/fixtures/`, or any external project directory that contains `prd.md` and `plan.md`.

## Setup

Install and configure Docker Sandboxes so `sbx` is available:

```bash
command -v sbx
```

For ChatGPT/Codex subscription auth, prefer OpenAI OAuth through Docker Sandbox:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
sbx secret set -g openai --oauth
```

Then verify a basic sandbox run:

```bash
sbx run codex .
```

No local `do-work` skill installation is required. Specode Loop ships its own
`specode-do-work` workflow skill and copies that runner-managed skill into the
target project before each sandbox run.

For API-key billing instead, use Docker's OpenAI secret or environment variables intentionally:

```bash
sbx secret set -g openai
```

or:

```bash
export OPENAI_API_KEY=...
```

## Usage

```bash
scripts/specode_loop.sh PROJECT_DIR [options]
```

Options:

- `--max-iterations N`: maximum sandbox iterations. Default: `10`.
- `--model MODEL`: Codex model for the run, passed to `codex exec -m`.
- `--effort EFFORT`: reasoning effort.
- `--reasoning-effort EFFORT`: alias for `--effort`.
- `-h`, `--help`: show help.

Allowed reasoning effort values:

```text
minimal, low, medium, high, xhigh
```

Example:

```bash
scripts/specode_loop.sh /path/to/project --max-iterations 10 --model YOUR_CODEX_MODEL --reasoning-effort medium
```

Before the first sandbox iteration, the runner syncs each required bundled
workflow skill from this repository into the target project's project-level
agent configuration. The initial required skill is copied from
`.agents/skills/specode-do-work` to
`PROJECT_DIR/.agents/skills/specode-do-work`.

## Script Defaults

The runner starts with these defaults in `scripts/specode_loop.sh`:

```bash
MAX_ITERATIONS="10"
MODEL=""
MODEL_REASONING_EFFORT=""
SPECODE_LOOP_VERBOSE="${SPECODE_LOOP_VERBOSE:-0}"
```

An empty `MODEL` means Codex uses its project/config/default model. An empty `MODEL_REASONING_EFFORT` means Codex uses its project/config/default reasoning effort.

## Environment Variables

### Runner

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPECODE_LOOP_VERBOSE` | `0` | Set to `1` to append the raw Docker Sandbox/Codex transcript to `specode_loop.log`. Default logs stay concise. |
| `OPENAI_API_KEY` | unset | Optional API-key auth path. Unset this when using subscription OAuth to avoid API billing. |
| `CODEX_API_KEY` | unset | Optional Codex/OpenAI API-key auth path. Unset this when using subscription OAuth. |
| `OPENAI_BASE_URL` | unset | Optional OpenAI-compatible base URL used by Codex/OpenAI tooling when configured. Present in `.env.example`. |

### E2E Test

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPECODE_LOOP_E2E_ENV` | unset | Optional env file loaded by `tests/specode_loop-e2e.sh`. Leave unset when using Docker Sandbox OAuth. |
| `SPECODE_LOOP_E2E_KEEP` | `0` | Set to `1` to keep the temporary e2e project for inspection. |
| `SPECODE_LOOP_E2E_MODEL` | unset | Optional model used by the real e2e test. Leave unset to use Codex's project/config/default model. |

### Mentioned But Not Active

| Variable | Status |
| --- | --- |
| `SPECODE_LOOP_ALLOW_API_BILLING` | Mentioned in older auth notes as a possible future guard, but not currently read by the scripts. |

## Logs

Specode Loop writes `specode_loop.log` in the target project directory.

Default logs include:

- preflight summary
- project paths
- synced `specode-do-work` bundled workflow skill path
- model and reasoning effort
- iteration start/end
- sentinel detection
- sandbox cleanup

Default logs do not include the raw Codex transcript or full skill contents.

Use verbose mode when debugging:

```bash
SPECODE_LOOP_VERBOSE=1 scripts/specode_loop.sh /path/to/project
```

## Repository Layout

```text
.
├── README.md
├── .env.example
├── .gitignore
├── .agents/
│   └── skills/
│       └── specode-do-work/
│           ├── SKILL.md
│           └── references/
│               └── workflow.txt
├── examples/
│   └── basic/
│       ├── prd.md
│       └── plan.md
├── plans/
│   └── specode_loop.md
├── prd/
│   └── specode_loop.md
├── scripts/
│   └── specode_loop.sh
└── tests/
    ├── fixtures/
    │   └── basic-project/
    │       ├── prd.md
    │       └── plan.md
    ├── specode_loop-e2e.sh
    └── specode_loop-regression.sh
```

Root-level `prd.md`, `plan.md`, `idea.md`, `prompt.md`, `.codex/` local Codex state, logs, secrets, and generated root `fixtures/` are intentionally ignored as local working files. The repository-owned bundled workflow skill lives under `.agents/skills/specode-do-work`.

## Tests

Regression tests use a fake `sbx` and do not launch a real sandbox:

```bash
bash tests/specode_loop-regression.sh
```

The real e2e test launches Docker Sandbox and Codex:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop-e2e.sh
```

Keep the temporary e2e project:

```bash
SPECODE_LOOP_E2E_KEEP=1 bash tests/specode_loop-e2e.sh
```

Use a specific e2e model:

```bash
SPECODE_LOOP_E2E_MODEL=YOUR_CODEX_MODEL bash tests/specode_loop-e2e.sh
```

## References

- Docker Codex agent docs: https://docs.docker.com/ai/sandboxes/agents/codex/
- Docker Sandbox credentials: https://docs.docker.com/ai/sandboxes/security/credentials/
- OpenAI Codex CLI reference: https://developers.openai.com/codex/cli/reference
- OpenAI Codex config basics: https://developers.openai.com/codex/config-basic
