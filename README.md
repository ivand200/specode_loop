# Specode Loop

Specode Loop runs Codex inside Docker Sandbox against a Target Project one plan
task at a time.

A Target Project needs two Planning Documents:

- a PRD document describing the requested behavior
- a plan document with ordered Markdown checkbox phases

By default those files are `prd.md` and `plan.md`. Use `--prd` and `--plan`
when a project uses different filenames.

During each sandbox iteration, Codex must finish exactly one eligible undone AFK
phase, mark only that phase complete, and print one success sentinel:

- `TASK DONE`
- `ALL TASKS DONE`

## Requirements

- Python 3.11+
- `uv`
- Docker Sandbox CLI (`sbx`)
- Codex auth available to Docker Sandbox

Check the sandbox CLI:

```bash
command -v sbx
```

For ChatGPT/Codex subscription auth, prefer Docker Sandbox OAuth:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
sbx secret set -g openai --oauth
sbx run codex .
```

For API-key billing, configure Docker's OpenAI secret instead:

```bash
sbx secret set -g openai
```

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
| `--max-iterations N` | `10` | Maximum sandbox iterations |
| `--model MODEL` | `gpt-5.5` | Codex model passed to `codex exec -m` |
| `--effort EFFORT` | `high` | Reasoning effort: `minimal`, `low`, `medium`, `high`, `xhigh` |
| `--reasoning-effort EFFORT` | `high` | Alias for `--effort` |

Custom Planning Document paths are resolved inside `PROJECT_DIR`:

```bash
uv run python scripts/specode_loop.py /path/to/project \
  --prd docs/product-requirements.md \
  --plan planning/implementation-plan.md
```

Absolute `--prd` and `--plan` paths are accepted only when they resolve inside
the Target Project.

## Workflow Skills

Specode Loop first looks for a host global `do-work` skill at:

- `$CODEX_HOME/skills/do-work`
- `~/.codex/skills/do-work`

When found, the runner copies it into the Target Project as
`.agents/skills/do-work` so sandboxed Codex can use it.

The repository also ships a fallback workflow skill at
`.agents/skills/specode-do-work`. Before each sandbox run, the runner copies
that directory into the Target Project as `.agents/skills/specode-do-work`.

The sandbox prompt tells Codex to use `do-work` first, then fall back to the
project-local `specode-do-work` skill when `do-work` is unavailable.

## Logs

Specode Loop writes `specode_loop.log` in the Target Project.

Default logs include preflight details, selected Planning Documents, synced
workflow skills, model and reasoning effort, iteration status, sentinel
detection, and sandbox cleanup. Raw Codex transcripts are included only when
`SPECODE_LOOP_VERBOSE=1`.

## Tests

Run the deterministic regression suite:

```bash
uv run pytest
```

Run the optional real E2E harness only when `sbx`, Docker Sandbox auth, network
access, and real Codex execution are available:

```bash
unset OPENAI_API_KEY CODEX_API_KEY
bash tests/specode_loop_python-e2e.sh
```

## More Detail

Architecture decisions live in `docs/adr/`. Root-level local planning files,
logs, secrets, `.codex/`, generated fixtures, and `/tasks` are intentionally
kept out of version control for local development.
