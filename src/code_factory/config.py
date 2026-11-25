"""Settings for code-factory, loaded from environment variables and the project's `.env` file.

New settings use the `CF_` prefix (for example `CF_CONCURRENCY`). The notification settings keep
the exact names used by the old agent farm (`NOTIFY_EMAIL`, `NOTIFY_ON`, `MSMTP_ACCOUNT`,
`NOTIFY_FROM_NAME`, `NOTIFY_FROM`) so an existing `.env` keeps working unchanged.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_PREFIX = "CF_"
DEFAULT_ENV_FILE = ".env"
DB_FILENAME = "factory.db"
CHECKPOINT_DB_FILENAME = "checkpoints.db"
LOOPBACK_HOSTNAMES = frozenset({"localhost"})
NOTIFY_EVENTS = frozenset({"ready", "needs_human"})


def expand_path(value: Path | str) -> Path:
    """Expand `~` and resolve a path to an absolute one.

    Args:
        value: A path, possibly starting with `~` or relative to the current directory.

    Returns:
        The absolute, resolved path. The path does not need to exist.
    """
    return Path(value).expanduser().resolve()


def is_loopback_host(host: str) -> bool:
    """Tell whether a host name or IP address refers to the loopback interface.

    Args:
        host: A host name (only `localhost` is accepted) or an IPv4/IPv6 address.

    Returns:
        True if the host is loopback-only, False otherwise.
    """
    candidate = host.strip().lower()
    if candidate in LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(candidate.strip("[]")).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    """Effective code-factory settings.

    Values come from (highest priority first) init arguments, environment variables and the
    `.env` file in the current directory.

    Attributes:
        agents_dir: Directory holding the agent role profiles (`<role>.md`).
        skills_dir: Directory holding the skills library (`<skill>/SKILL.md`).
        data_dir: Directory for runtime data (databases, worktrees, logs).
        concurrency: Number of tasks the worker runs at once (1 or 2).
        usage_limit_5h: Pause work when the 5-hour usage window reaches this percentage.
        usage_limit_week: Pause work when the weekly usage window reaches this percentage.
        api_host: Host the HTTP API binds to; must be loopback.
        api_port: Port the HTTP API binds to.
        api_token: Bearer token required by the HTTP API.
        allow_api_key: Allow running while `ANTHROPIC_API_KEY` is set (switches billing to the API).
        notify_email: Recipient of notification emails; empty disables email.
        notify_on: Events that trigger a notification.
        msmtp_account: msmtp account (from `~/.msmtprc`) used to send email.
        notify_from_name: Sender name shown in the inbox.
        notify_from: Sender address; when unset, the sender derives it from `notify_email`.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    agents_dir: Path = Path("~/agents/agents")
    skills_dir: Path = Path("~/skills")
    data_dir: Path = Path("~/.local/share/code-factory")

    concurrency: int = Field(default=1, ge=1, le=2)
    usage_limit_5h: int = Field(default=75, ge=1, le=100)
    usage_limit_week: int = Field(default=90, ge=1, le=100)

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8765, ge=1, le=65535)
    api_token: SecretStr | None = None
    allow_api_key: bool = False

    notify_email: str = Field(
        default="", validation_alias=AliasChoices("NOTIFY_EMAIL", "notify_email")
    )
    notify_on: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["ready", "needs_human"],
        validation_alias=AliasChoices("NOTIFY_ON", "notify_on"),
    )
    msmtp_account: str = Field(
        default="gmail", validation_alias=AliasChoices("MSMTP_ACCOUNT", "msmtp_account")
    )
    notify_from_name: str = Field(
        default="Agent Farm",
        validation_alias=AliasChoices("NOTIFY_FROM_NAME", "notify_from_name"),
    )
    notify_from: str | None = Field(
        default=None, validation_alias=AliasChoices("NOTIFY_FROM", "notify_from")
    )

    @field_validator("agents_dir", "skills_dir", "data_dir", mode="after")
    @classmethod
    def _expand_paths(cls, value: Path) -> Path:
        """Expand `~` and make directory settings absolute."""
        return expand_path(value)

    @field_validator("api_host", mode="after")
    @classmethod
    def _require_loopback(cls, value: str) -> str:
        """Reject any API host that is not loopback, so the API is never exposed."""
        if not is_loopback_host(value):
            msg = f"api_host must be loopback (127.0.0.1, ::1 or localhost), got {value!r}"
            raise ValueError(msg)
        return value.strip()

    @field_validator("notify_on", mode="before")
    @classmethod
    def _split_notify_on(cls, value: object) -> object:
        """Accept a comma-separated string (as written in `.env`) as well as a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("notify_on", mode="after")
    @classmethod
    def _check_notify_events(cls, value: list[str]) -> list[str]:
        """Normalise event names and reject unknown ones."""
        events = [item.lower() for item in value]
        unknown = sorted(set(events) - NOTIFY_EVENTS)
        if unknown:
            allowed = ", ".join(sorted(NOTIFY_EVENTS))
            msg = f"unknown NOTIFY_ON event(s): {', '.join(unknown)} (allowed: {allowed})"
            raise ValueError(msg)
        return events

    @field_validator("notify_from", mode="after")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        """Treat an empty `NOTIFY_FROM=` as unset."""
        return value or None

    @field_validator("api_token", mode="after")
    @classmethod
    def _empty_token_to_none(cls, value: SecretStr | None) -> SecretStr | None:
        """Treat an empty `CF_API_TOKEN=` as unset."""
        if value is None or not value.get_secret_value():
            return None
        return value

    @property
    def db_path(self) -> Path:
        """Path of the task/event store database, under `data_dir`."""
        return self.data_dir / DB_FILENAME

    @property
    def checkpoint_db_path(self) -> Path:
        """Path of the LangGraph checkpoint database, under `data_dir`."""
        return self.data_dir / CHECKPOINT_DB_FILENAME


def load_settings(env_file: Path | str | None = DEFAULT_ENV_FILE) -> Settings:
    """Load settings from the environment and an optional `.env` file.

    Args:
        env_file: The `.env` file to read; None reads only environment variables.

    Returns:
        The validated settings.

    Raises:
        pydantic.ValidationError: If a setting has an invalid value.
    """
    return Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
