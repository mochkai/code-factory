from pathlib import Path

import pytest
from pydantic import ValidationError

from code_factory.config import (
    Settings,
    is_loopback_host,
    load_settings,
    normalize_loopback_host,
    resolve_env_file,
)


def test_defaults() -> None:
    s = load_settings()
    home = Path.home()
    assert s.agents_dir == (home / "agents/agents").resolve()
    assert s.skills_dir == (home / "skills").resolve()
    assert s.data_dir == (home / ".local/share/code-factory").resolve()
    assert s.db_path == s.data_dir / "factory.db"
    assert s.checkpoint_db_path == s.data_dir / "checkpoints.db"
    assert s.concurrency == 1
    assert s.usage_limit_5h == 75
    assert s.usage_limit_week == 90
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8765
    assert s.api_token is None
    assert s.allow_api_key is False
    assert s.notify_email == ""
    assert s.notify_on == ["ready", "needs_human"]
    assert s.msmtp_account == "gmail"
    assert s.notify_from_name == "Agent Farm"
    assert s.notify_from is None


def test_paths_expand_and_derive() -> None:
    s = Settings(data_dir=Path("~/somewhere"), agents_dir=Path("rel/agents"))
    assert s.data_dir == Path.home() / "somewhere"
    assert s.agents_dir == (Path.cwd() / "rel/agents").resolve()
    assert s.db_path == Path.home() / "somewhere" / "factory.db"


# --- env file location ---


def test_env_file_xdg_default(isolated_env: Path) -> None:
    assert resolve_env_file() == isolated_env / "xdg" / "code-factory" / ".env"


def test_env_file_without_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert resolve_env_file() == (Path.home() / ".config/code-factory/.env").resolve()


def test_env_file_relative_xdg_ignored() -> None:
    expected = (Path.home() / ".config/code-factory/.env").resolve()
    assert resolve_env_file({"XDG_CONFIG_HOME": "relative/dir"}) == expected


def test_env_file_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "custom.env"
    custom.write_text("MSMTP_ACCOUNT=custom\n", encoding="utf-8")
    monkeypatch.setenv("CF_ENV_FILE", str(custom))
    assert resolve_env_file() == custom
    assert load_settings().msmtp_account == "custom"


def test_env_file_override_expands_home() -> None:
    assert resolve_env_file({"CF_ENV_FILE": "~/x.env"}) == Path.home() / "x.env"


def test_dotenv_in_cwd_is_not_read() -> None:
    Path(".env").write_text("CF_ALLOW_API_KEY=true\nMSMTP_ACCOUNT=evil\n", encoding="utf-8")
    s = load_settings()
    assert s.allow_api_key is False
    assert s.msmtp_account == "gmail"
    assert Settings().allow_api_key is False


def test_default_env_file_is_read(env_file: Path) -> None:
    env_file.write_text("NOTIFY_ON=ready, needs_human\nCF_CONCURRENCY=2\n", encoding="utf-8")
    s = load_settings()
    assert s.notify_on == ["ready", "needs_human"]
    assert s.concurrency == 2


# --- validation ---


@pytest.mark.parametrize("value", [1, 2])
def test_concurrency_allowed(value: int) -> None:
    assert Settings(concurrency=value).concurrency == value


@pytest.mark.parametrize("value", [0, 3])
def test_concurrency_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(concurrency=value)


@pytest.mark.parametrize(
    ("host", "normalized"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("127.0.0.2", "127.0.0.2"),
        ("::1", "::1"),
        ("[::1]", "::1"),
        ("0:0:0:0:0:0:0:1", "::1"),
        (" LocalHost ", "localhost"),
    ],
)
def test_loopback_hosts_normalized(host: str, normalized: str) -> None:
    assert is_loopback_host(host)
    assert normalize_loopback_host(host) == normalized
    assert Settings(api_host=host).api_host == normalized


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "192.168.1.10", "::", "example.com", "", "::1%lo", "[::1%lo]", "[::1", "::1]"],
)
def test_non_loopback_hosts_rejected(host: str) -> None:
    assert not is_loopback_host(host)
    with pytest.raises(ValidationError, match="api_host"):
        Settings(api_host=host)


def test_api_host_from_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_API_HOST", "0.0.0.0")
    with pytest.raises(ValidationError):
        load_settings()


def test_cf_prefixed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_CONCURRENCY", "2")
    monkeypatch.setenv("CF_API_TOKEN", "s3cret")
    monkeypatch.setenv("CF_ALLOW_API_KEY", "true")
    s = load_settings()
    assert s.concurrency == 2
    assert s.api_token is not None
    assert s.api_token.get_secret_value() == "s3cret"
    assert s.allow_api_key is True


def test_notify_keys_load_from_dotenv(env_file: Path) -> None:
    env_file.write_text(
        "NOTIFY_EMAIL=you+agentfarm@example.com\n"
        "NOTIFY_ON=ready\n"
        "MSMTP_ACCOUNT=work\n"
        'NOTIFY_FROM_NAME="Agent Farm"\n'
        "NOTIFY_FROM=you@example.com\n"
        "CF_USAGE_LIMIT_5H=50\n",
        encoding="utf-8",
    )
    s = load_settings()
    assert s.notify_email == "you+agentfarm@example.com"
    assert s.notify_on == ["ready"]
    assert s.msmtp_account == "work"
    assert s.notify_from_name == "Agent Farm"
    assert s.notify_from == "you@example.com"
    assert s.usage_limit_5h == 50


def test_cf_prefixed_notify_keys_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_NOTIFY_EMAIL", "you@example.com")
    monkeypatch.setenv("CF_MSMTP_ACCOUNT", "other")
    monkeypatch.setenv("CF_NOTIFY_ON", "ready")
    s = load_settings()
    assert s.notify_email == ""
    assert s.msmtp_account == "gmail"
    assert s.notify_on == ["ready", "needs_human"]


def test_env_var_overrides_dotenv(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file.write_text("MSMTP_ACCOUNT=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("MSMTP_ACCOUNT", "fromenv")
    assert load_settings().msmtp_account == "fromenv"


def test_empty_notify_from_is_none(env_file: Path) -> None:
    env_file.write_text("NOTIFY_FROM=\n", encoding="utf-8")
    assert load_settings().notify_from is None


def test_notify_on_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_ON", "needs_human,ready,NEEDS_HUMAN,ready")
    assert load_settings().notify_on == ["needs_human", "ready"]


def test_unknown_notify_event_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_ON", "ready,bogus")
    with pytest.raises(ValidationError, match="bogus"):
        load_settings()


def test_empty_api_token_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_API_TOKEN", "")
    assert load_settings().api_token is None
