import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_factory import cli
from code_factory.config import Settings
from code_factory.doctor import (
    CheckResult,
    CommandResult,
    Status,
    check_api_key,
    check_claude,
    check_gh,
    check_git,
    check_msmtp,
    check_python,
    has_blocking_failure,
    list_profiles,
    list_skills,
    parse_claude_auth,
    run_checks,
)

CLAUDE_OK = json.dumps(
    {
        "loggedIn": True,
        "authMethod": "claude.ai",
        "subscriptionType": "pro",
        "email": "someone@example.com",
    }
)


def which_all(name: str) -> str | None:
    return f"/usr/bin/{name}"


def which_none(name: str) -> str | None:
    return None


class FakeRunner:
    """Records calls and returns canned results keyed by the first two args."""

    def __init__(self, results: dict[tuple[str, ...], CommandResult]) -> None:
        self.results = results
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> CommandResult:
        self.calls.append(list(args))
        return self.results.get(tuple(args), CommandResult(returncode=1))


def healthy_runner() -> FakeRunner:
    return FakeRunner(
        {
            ("gh", "auth", "status"): CommandResult(0),
            ("claude", "auth", "status"): CommandResult(0, stdout=CLAUDE_OK),
        }
    )


@pytest.fixture
def dirs(tmp_path: Path) -> Settings:
    agents = tmp_path / "agents"
    skills = tmp_path / "skills"
    agents.mkdir()
    (agents / "coder.md").write_text("x")
    (agents / "tester.md").write_text("x")
    (skills / "debugging").mkdir(parents=True)
    (skills / "debugging" / "SKILL.md").write_text("x")
    (skills / "not-a-skill").mkdir()
    return Settings(agents_dir=agents, skills_dir=skills)


def test_python_version() -> None:
    assert check_python((3, 12)).status is Status.OK
    assert check_python((3, 11)).status is Status.FAIL
    assert check_python().status is Status.OK


def test_git() -> None:
    assert check_git(which_all).status is Status.OK
    assert check_git(which_none).status is Status.FAIL


def test_gh_logged_in_and_out() -> None:
    assert check_gh(which_all, healthy_runner()).status is Status.OK
    assert check_gh(which_all, FakeRunner({})).status is Status.FAIL
    assert check_gh(which_none, healthy_runner()).status is Status.FAIL


def test_claude_logged_in_hides_email() -> None:
    result = check_claude(which_all, healthy_runner())
    assert result.status is Status.OK
    assert "pro" in result.detail
    assert "example.com" not in result.detail


@pytest.mark.parametrize(
    "stdout",
    ["not json", "[]", json.dumps({"loggedIn": False})],
)
def test_claude_not_logged_in(stdout: str) -> None:
    run = FakeRunner({("claude", "auth", "status"): CommandResult(0, stdout=stdout)})
    assert check_claude(which_all, run).status is Status.FAIL


def test_claude_missing() -> None:
    run = healthy_runner()
    assert check_claude(which_none, run).status is Status.FAIL
    assert run.calls == []


def test_parse_claude_auth() -> None:
    assert parse_claude_auth(CLAUDE_OK) == (True, "logged in via claude.ai (pro)")


def test_api_key() -> None:
    assert check_api_key({}, allow_api_key=False).status is Status.OK
    assert check_api_key({"ANTHROPIC_API_KEY": ""}, allow_api_key=False).status is Status.OK
    assert check_api_key({"ANTHROPIC_API_KEY": "k"}, allow_api_key=False).status is Status.FAIL
    assert check_api_key({"ANTHROPIC_API_KEY": "k"}, allow_api_key=True).status is Status.WARN


def test_msmtp_is_optional() -> None:
    result = check_msmtp(which_none)
    assert result.status is Status.WARN
    assert not result.blocking


def test_listings(dirs: Settings) -> None:
    assert list_profiles(dirs.agents_dir) == ["coder", "tester"]
    assert list_skills(dirs.skills_dir) == ["debugging"]


def test_run_checks_all_ok(dirs: Settings) -> None:
    results = run_checks(dirs, run=healthy_runner(), which=which_all, env={})
    assert [r.status for r in results] == [Status.OK] * len(results)
    agents = next(r for r in results if r.name == "agents_dir")
    assert "coder, tester" in agents.detail
    assert not has_blocking_failure(results)


def test_run_checks_missing_dirs(tmp_path: Path) -> None:
    settings = Settings(agents_dir=tmp_path / "nope", skills_dir=tmp_path)
    results = run_checks(settings, run=healthy_runner(), which=which_all, env={})
    by_name = {r.name: r for r in results}
    assert by_name["agents_dir"].status is Status.FAIL
    assert by_name["skills_dir"].status is Status.FAIL  # exists but has no skills
    assert has_blocking_failure(results)


def test_run_checks_api_key_blocks(dirs: Settings) -> None:
    results = run_checks(
        dirs, run=healthy_runner(), which=which_all, env={"ANTHROPIC_API_KEY": "k"}
    )
    assert has_blocking_failure(results)


@pytest.mark.parametrize(
    ("results", "exit_code"),
    [
        ([CheckResult("a", Status.OK, "fine")], 0),
        ([CheckResult("a", Status.WARN, "meh", required=False)], 0),
        ([CheckResult("a", Status.FAIL, "broken", required=False)], 0),
        ([CheckResult("a", Status.FAIL, "broken")], 1),
    ],
)
def test_doctor_command_exit_code(
    monkeypatch: pytest.MonkeyPatch, results: list[CheckResult], exit_code: int
) -> None:
    monkeypatch.setattr(cli, "run_checks", lambda settings: results)
    result = CliRunner().invoke(cli.app, ["doctor"])
    assert result.exit_code == exit_code, result.output
