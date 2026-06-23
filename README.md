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

Create a disposable copy of the multi-step example target project:

```bash
DEMO_PROJECT="$(mktemp -d "${TMPDIR:-/tmp}/specode-loop-demo.XXXXXX")"
cp -R examples/basic/. "$DEMO_PROJECT"
uv run python scripts/specode_loop.py "$DEMO_PROJECT"
```

Use a specific model or reasoning effort when you want to override your Codex defaults:

```bash
uv run python scripts/specode_loop.py "$DEMO_PROJECT" --model YOUR_CODEX_MODEL --reasoning-effort medium
```

The example completes three deterministic plan phases, then stops after the
runner observes `ALL TASKS DONE`.

Verbose transcript logging:

```bash
SPECODE_LOOP_VERBOSE=1 uv run python scripts/specode_loop.py "$DEMO_PROJECT"
```

The repository root is the source repo for Specode Loop. Target projects live in `examples/`, `tests/fixtures/`, or any external project directory that contains `prd.md` and `plan.md`.

The Python runner is the transitional side-by-side port of the original shell
runner. It is intended to replace the shell implementation after parity is
proven, but the shell command remains present and documented during that
transition.

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

Python port:

```bash
uv run python scripts/specode_loop.py PROJECT_DIR [options]
```

Shell runner:

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
uv run python scripts/specode_loop.py /path/to/project --max-iterations 10 --model YOUR_CODEX_MODEL --reasoning-effort medium
```

Equivalent shell invocation:

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
| `SPECODE_LOOP_PYTHON_E2E_ENV` | `SPECODE_LOOP_E2E_ENV` | Optional env file loaded by `tests/specode_loop_python-e2e.sh`. |
| `SPECODE_LOOP_PYTHON_E2E_KEEP` | `0` | Set to `1` to keep the Python e2e project, stdout/stderr transcript, and log for inspection. |
| `SPECODE_LOOP_KEEP_E2E_ARTIFACTS` | `0` | Alias accepted by the Python e2e script for keeping artifacts. |
| `SPECODE_LOOP_PYTHON_E2E_MODEL` | `SPECODE_LOOP_E2E_MODEL` | Optional model used by the Python real e2e test. |

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
SPECODE_LOOP_VERBOSE=1 uv run python scripts/specode_loop.py /path/to/project
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
│   ├── specode_loop.py
│   └── specode_loop.sh
└── tests/
    ├── fixtures/
    │   └── basic-project/
    │       ├── prd.md
    │       └── plan.md
    ├── test_specode_loop_python.py
    ├── specode_loop_python-e2e.sh
    ├── specode_loop-e2e.sh
    └── specode_loop-regression.sh
```

Root-level `prd.md`, `plan.md`, `idea.md`, `prompt.md`, `.codex/` local Codex state, logs, secrets, and generated root `fixtures/` are intentionally ignored as local working files. The repository-owned bundled workflow skill lives under `.agents/skills/specode-do-work`.

## Tests

The default Python regression suite uses a fake `sbx` and does not launch a
real Docker Sandbox:

```bash
uv run pytest
```

The shell regression suite also uses a fake `sbx`:

```bash
bash tests/specode_loop-regression.sh
```

Real e2e tests are optional and manual because they require `sbx`, Docker
Sandbox OAuth, network access, and real Codex execution.

Run the Python real e2e path against a copy of `examples/basic`:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_python-e2e.sh
```

Keep the temporary Python e2e project, stdout/stderr transcript, and
`specode_loop.log` for inspection:

```bash
SPECODE_LOOP_PYTHON_E2E_KEEP=1 bash tests/specode_loop_python-e2e.sh
```

`SPECODE_LOOP_KEEP_E2E_ARTIFACTS=1` is accepted as an alias.

Use a specific Python e2e model:

```bash
SPECODE_LOOP_PYTHON_E2E_MODEL=YOUR_CODEX_MODEL bash tests/specode_loop_python-e2e.sh
```

Run the shell real e2e path:

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
