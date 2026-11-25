# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- M0 scaffold: uv project (`code_factory` package, src layout) with the `cf` console script.
- `config.py`: pydantic-settings `Settings` loaded from env vars and one fixed `.env` file (`$CF_ENV_FILE`, else `$XDG_CONFIG_HOME/code-factory/.env`, default `~/.config/code-factory/.env`; `./.env` in the current directory is never read). Loopback-only API host validation (stored normalised, e.g. `[::1]` → `::1`; zone ids and malformed brackets rejected), concurrency limit (1-2) and the existing `NOTIFY_*` / `MSMTP_ACCOUNT` notification keys (only those exact names; `NOTIFY_ON` is de-duplicated).
- `cf --version`, `cf config` (env file path and effective settings, secrets and email redacted; invalid settings are reported by field without echoing values) and `cf doctor` (Python, git, gh login, claude login, `ANTHROPIC_API_KEY` guard, agents/skills directories, env file present and `0600`, msmtp).
- `.env.example` documenting every setting.
- Tooling: ruff (lint + format), pyright (strict for `src/`), pytest with a `live` marker deselected by default.
- GitHub Actions CI: lint, format check, type check and tests.
- Project `CLAUDE.md` with notes for agents working on this repo.
