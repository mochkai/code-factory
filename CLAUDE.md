# code-factory: notes for agents

code-factory is a Python harness that runs Claude coding agents through plan, code, test, review and a pull request. The approved design and milestones are in [docs/plan.md](docs/plan.md): read it before starting, and build only the milestone you were given.

## Stack

Python 3.12+, uv, pydantic v2 + pydantic-settings, typer. Later milestones add langgraph, claude-agent-sdk, FastAPI; do not add them ahead of their milestone. Tools: ruff, pyright (strict), pytest + pytest-asyncio.

## Layout

```
src/code_factory/   package (config.py, doctor.py, cli.py, ...)
tests/              pytest tests (conftest.py isolates env vars and the cwd)
docs/plan.md        design and milestones
.env.example        every setting; the real .env is git-ignored
```

## Commands

```sh
uv sync --all-groups
uv run ruff check       # lint (use --fix for autofixes)
uv run ruff format      # format
uv run pyright          # type check
uv run pytest           # tests; live tests are deselected by default
```

Run all four before reporting work as done.

## Conventions

- Google-style docstrings on every public module, class and function.
- Strict typing in `src/` (pyright strict); no bare `Any` without a comment explaining why.
- Keep logic in pure, injectable functions (see `doctor.py`) so it can be tested without real subprocesses.
- Update `changelog.md` (Keep a Changelog, `## [Unreleased]`) with every change.
- Work on a branch and open a pull request; never commit to `master` directly. The human merges.
- Never call the real Claude in tests. Use recorded/mocked runners; tests that must hit Claude are marked `@pytest.mark.live` and are opt-in (`uv run pytest -m live`), never run in CI.
- Never print or commit `.env` values. `cf config` redacts secrets and email addresses; keep it that way for new settings (use `SecretStr` or add the field to `SENSITIVE_FIELDS` in `cli.py`).
- The HTTP API binds to loopback only; `ANTHROPIC_API_KEY` must stay unset unless `CF_ALLOW_API_KEY=true`.
