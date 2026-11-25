"""The `cf` command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr, ValidationError

from code_factory import __version__
from code_factory.config import Settings, load_settings, resolve_env_file
from code_factory.doctor import Status, has_blocking_failure, run_checks

REDACTED = "***"
# Settings that identify the user and are shown redacted even though they are not SecretStr.
SENSITIVE_FIELDS = frozenset({"notify_email", "notify_from"})

app = typer.Typer(
    name="cf",
    help="code-factory: drive Claude coding agents from task to pull request.",
    no_args_is_help=True,
    add_completion=False,
)

_STATUS_LABELS = {Status.OK: "OK  ", Status.WARN: "WARN", Status.FAIL: "FAIL"}


def _version_callback(value: bool) -> None:
    """Print the version and exit when `--version` is given."""
    if value:
        typer.echo(f"cf {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """code-factory: drive Claude coding agents from task to pull request."""


def format_validation_error(exc: ValidationError) -> str:
    """Describe invalid settings by field and message only, never echoing the input values.

    Args:
        exc: The validation error raised while loading settings.

    Returns:
        One line per error, e.g. `  api_host: Value error, api_host must be loopback ...`.
    """
    lines = ["Invalid settings:"]
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error["loc"]) or "(settings)"
        lines.append(f"  {location}: {error['msg']}")
    return "\n".join(lines)


def _settings_or_exit(env_file: Path) -> Settings:
    """Load settings from `env_file`, turning a validation error into a clean CLI error."""
    try:
        return load_settings(env_file)
    except ValidationError as exc:
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=2) from None


def format_setting(name: str, value: object) -> str:
    """Render one setting for display, redacting secrets and personal data.

    Args:
        name: The setting's field name.
        value: The setting's value.

    Returns:
        The display string.
    """
    if value is None or value == "":
        return "(unset)"
    if isinstance(value, SecretStr) or name in SENSITIVE_FIELDS:
        return REDACTED
    if isinstance(value, list):
        items: list[object] = value  # pyright: ignore[reportUnknownVariableType]
        return ",".join(str(item) for item in items)
    return str(value)


def settings_rows(settings: Settings) -> list[tuple[str, str]]:
    """Build the (name, display value) rows shown by `cf config`.

    Args:
        settings: The effective settings.

    Returns:
        Rows in field order, followed by the derived database paths.
    """
    rows = [
        (name, format_setting(name, getattr(settings, name)))
        for name in type(settings).model_fields
    ]
    rows.append(("db_path", str(settings.db_path)))
    rows.append(("checkpoint_db_path", str(settings.checkpoint_db_path)))
    return rows


@app.command("config")
def config_command() -> None:
    """Print the effective settings, with secrets redacted."""
    env_file = resolve_env_file()
    rows = settings_rows(_settings_or_exit(env_file))
    state = "" if env_file.is_file() else " (not found)"
    typer.echo(f"env file: {env_file}{state}\n")
    width = max(len(name) for name, _ in rows)
    typer.echo(f"{'setting':<{width}}  value")
    typer.echo(f"{'-' * width}  {'-' * 5}")
    for name, value in rows:
        typer.echo(f"{name:<{width}}  {value}")


@app.command("doctor")
def doctor_command() -> None:
    """Check that the tools and logins code-factory needs are in place."""
    env_file = resolve_env_file()
    results = run_checks(_settings_or_exit(env_file), env_file)
    width = max(len(r.name) for r in results)
    for r in results:
        suffix = "" if r.required else " (optional)"
        typer.echo(f"[{_STATUS_LABELS[r.status]}] {r.name:<{width}}  {r.detail}{suffix}")
    if has_blocking_failure(results):
        typer.echo("\ncf doctor: required checks failed.", err=True)
        raise typer.Exit(code=1)
    typer.echo("\ncf doctor: all required checks passed.")
