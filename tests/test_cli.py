from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_factory import __version__
from code_factory.cli import app

runner = CliRunner()


def _rows(output: str) -> dict[str, str]:
    """Parse the `cf config` table (after the env-file line, blank line and header)."""
    lines = output.splitlines()
    start = lines.index("") + 3
    return {line.split()[0]: line.split(maxsplit=1)[1] for line in lines[start:] if line}


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_config_redacts_secrets(env_file: Path) -> None:
    env_file.write_text(
        "NOTIFY_EMAIL=you+agentfarm@example.com\n"
        "NOTIFY_FROM=you@example.com\n"
        "CF_API_TOKEN=super-secret-token\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0, result.output
    assert "example.com" not in result.output
    assert "super-secret-token" not in result.output
    rows = _rows(result.output)
    assert rows["notify_email"] == "***"
    assert rows["notify_from"] == "***"
    assert rows["api_token"] == "***"
    assert rows["notify_from_name"] == "Agent Farm"
    assert rows["db_path"].endswith("factory.db")


def test_config_prints_env_file(env_file: Path) -> None:
    result = runner.invoke(app, ["config"])
    assert f"env file: {env_file} (not found)" in result.output
    env_file.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["config"])
    assert f"env file: {env_file}\n" in result.output


def test_config_unset_values() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "(unset)" in result.output


def test_config_invalid_settings_hide_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_API_HOST", "10.9.8.7")
    monkeypatch.setenv("CF_CONCURRENCY", "99")
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 2
    assert "api_host" in result.output
    assert "concurrency" in result.output
    assert "10.9.8.7" not in result.output
    assert "99" not in result.output
