"""Shared fixtures: isolate every test from the real environment and the real .env file."""

import os
from pathlib import Path

import pytest

_ISOLATED_PREFIXES = ("cf_", "notify_", "msmtp_")
_ISOLATED_NAMES = {"anthropic_api_key", "xdg_config_home"}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run each test in an empty cwd, with XDG_CONFIG_HOME in tmp and no code-factory env vars.

    Env var names are matched case-insensitively, because pydantic-settings reads them that way.
    """
    for key in list(os.environ):
        lowered = key.lower()
        if lowered.startswith(_ISOLATED_PREFIXES) or lowered in _ISOLATED_NAMES:
            monkeypatch.delenv(key, raising=False)
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return tmp_path


@pytest.fixture
def env_file(isolated_env: Path) -> Path:
    """The default .env location under the isolated XDG_CONFIG_HOME (parent dir created)."""
    path = isolated_env / "xdg" / "code-factory" / ".env"
    path.parent.mkdir(parents=True)
    return path
