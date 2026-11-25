from pathlib import Path

import pytest
from pydantic import ValidationError

from code_factory.config import Settings, is_loopback_host, load_settings


def test_defaults() -> None:
    s = load_settings(env_file=None)
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


def test_paths_expand_and_derive(tmp_path: Path) -> None:
    s = Settings(data_dir=Path("~/somewhere"), agents_dir=Path("rel/agents"))
    assert s.data_dir == Path.home() / "somewhere"
    assert s.agents_dir == (tmp_path / "rel/agents").resolve()
    assert s.db_path == Path.home() / "somewhere" / "factory.db"


@pytest.mark.parametrize("value", [1, 2])
def test_concurrency_allowed(value: int) -> None:
    assert Settings(concurrency=value).concurrency == value


@pytest.mark.parametrize("value", [0, 3])
def test_concurrency_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(concurrency=value)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "[::1]", "localhost"])
def test_loopback_hosts_accepted(host: str) -> None:
    assert is_loopback_host(host)
    Settings(api_host=host)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com", ""])
def test_non_loopback_hosts_rejected(host: str) -> None:
    assert not is_loopback_host(host)
    with pytest.raises(ValidationError, match="loopback"):
        Settings(api_host=host)


def test_api_host_from_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_API_HOST", "0.0.0.0")
    with pytest.raises(ValidationError):
        load_settings(env_file=None)


def test_cf_prefixed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_CONCURRENCY", "2")
    monkeypatch.setenv("CF_API_TOKEN", "s3cret")
    monkeypatch.setenv("CF_ALLOW_API_KEY", "true")
    s = load_settings(env_file=None)
    assert s.concurrency == 2
    assert s.api_token is not None
    assert s.api_token.get_secret_value() == "s3cret"
    assert s.allow_api_key is True


def test_notify_keys_load_from_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NOTIFY_EMAIL=you+agentfarm@example.com\n"
        "NOTIFY_ON=ready\n"
        "MSMTP_ACCOUNT=work\n"
        'NOTIFY_FROM_NAME="Agent Farm"\n'
        "NOTIFY_FROM=you@example.com\n"
        "CF_USAGE_LIMIT_5H=50\n",
        encoding="utf-8",
    )
    s = load_settings(env_file=env_file)
    assert s.notify_email == "you+agentfarm@example.com"
    assert s.notify_on == ["ready"]
    assert s.msmtp_account == "work"
    assert s.notify_from_name == "Agent Farm"
    assert s.notify_from == "you@example.com"
    assert s.usage_limit_5h == 50


def test_dotenv_in_cwd_is_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NOTIFY_ON=ready, needs_human\n", encoding="utf-8")
    assert load_settings().notify_on == ["ready", "needs_human"]


def test_env_var_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("MSMTP_ACCOUNT=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("MSMTP_ACCOUNT", "fromenv")
    assert load_settings().msmtp_account == "fromenv"


def test_empty_notify_from_is_none(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NOTIFY_FROM=\n", encoding="utf-8")
    assert load_settings().notify_from is None


def test_unknown_notify_event_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_ON", "ready,bogus")
    with pytest.raises(ValidationError, match="bogus"):
        load_settings(env_file=None)


def test_empty_api_token_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_API_TOKEN", "")
    assert load_settings(env_file=None).api_token is None
