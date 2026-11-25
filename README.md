# code-factory

A LangGraph-based harness for Claude coding agents. It takes a task through plan, code, test, review and a pull request, and records every step in a local event store that a CLI, an HTTP API and a future dashboard can read.

**Status: early development (M0, scaffold).** Only configuration and environment checks exist so far. See [docs/plan.md](docs/plan.md) for the design and milestones.

The agent instructions it uses live in a separate repo, [mochkai/agents](https://github.com/mochkai/agents), and skills come from [mochkai/skills](https://github.com/mochkai/skills).

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- `git`, the GitHub CLI `gh` (logged in) and the `claude` CLI (logged in with your Claude account)
- `msmtp` (optional, for email notifications)
- `ANTHROPIC_API_KEY` must **not** be set: it would switch billing from your Claude login to the API

## Quickstart

```sh
uv sync                 # create .venv and install

# optional: settings file (a fixed location; see Configuration)
mkdir -p ~/.config/code-factory
cp .env.example ~/.config/code-factory/.env
chmod 600 ~/.config/code-factory/.env

uv run cf doctor        # check tools, logins, directories and the settings file
uv run cf config        # show the effective settings (secrets redacted)
```

## Configuration

Settings come from environment variables and one `.env` file (environment variables win). The file is `$CF_ENV_FILE` if set, otherwise `$XDG_CONFIG_HOME/code-factory/.env` (default `~/.config/code-factory/.env`). A `.env` in the current directory is **never** read, so running `cf` inside another repo cannot pick up that repo's settings. `cf config` prints which file was used, and `cf doctor` warns if it is missing or readable by others (it should be `chmod 600`). New settings use the `CF_` prefix (`CF_CONCURRENCY`, `CF_API_TOKEN`, ...); the notification keys keep the old agent farm names (`NOTIFY_EMAIL`, `NOTIFY_ON`, `MSMTP_ACCOUNT`, `NOTIFY_FROM_NAME`, `NOTIFY_FROM`). See [.env.example](.env.example) for every setting.

## Development

```sh
uv sync --all-groups
uv run ruff check          # lint
uv run ruff format         # format
uv run pyright             # type check (strict for src/)
uv run pytest              # tests (live Claude tests are excluded)
uv run pytest -m live      # opt-in tests that call the real Claude (uses quota)
```

CI runs lint, format check, type check and tests on every push and pull request.
