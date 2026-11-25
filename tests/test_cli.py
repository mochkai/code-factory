from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_factory import __version__
from code_factory.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_config_redacts_secrets(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "NOTIFY_EMAIL=you+agentfarm@example.com\n"
        "NOTIFY_FROM=you@example.com\n"
        "CF_API_TOKEN=super-secret-token\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0, result.output
    assert "example.com" not in result.output
    assert "super-secret-token" not in result.output
    lines = {line.split()[0]: line.split()[1] for line in result.output.splitlines()[2:]}
    assert lines["notify_email"] == "***"
    assert lines["notify_from"] == "***"
    assert lines["api_token"] == "***"
    assert lines["notify_from_name"] == "Agent"  # "Agent Farm", first token
    assert lines["db_path"].endswith("factory.db")


def test_config_unset_values() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "(unset)" in result.output


def test_config_invalid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_API_HOST", "0.0.0.0")
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 2
