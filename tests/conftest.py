"""Shared fixtures: isolate every test from the real environment and the real .env file."""

import os
from pathlib import Path

import pytest

_ISOLATED_PREFIXES = ("CF_", "NOTIFY_", "MSMTP_")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run each test in an empty temp dir with no code-factory env vars set."""
    for key in list(os.environ):
        if key.startswith(_ISOLATED_PREFIXES) or key == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path
