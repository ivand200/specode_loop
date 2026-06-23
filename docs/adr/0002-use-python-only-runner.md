# Use a Python-Only Runner

Specode Loop will use `scripts/specode_loop.py` as its only supported user-facing runner.

The canonical invocation is `uv run python scripts/specode_loop.py PROJECT_DIR`. The Python runner owns command parsing, Planning Document preflight, bundled workflow skill sync, prompt construction, Docker Sandbox invocation, logging, cleanup, and success sentinel handling.

The runner uses only Python standard-library modules at runtime. Development tooling can use repository dependencies such as pytest through `uv run pytest`, but normal runner behavior must stay clone-and-run friendly and must not require third-party Python packages.
