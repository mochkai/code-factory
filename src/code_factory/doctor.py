"""Environment checks behind `cf doctor`.

Every check is a small function that takes its dependencies (a command runner, a `which`
lookup, the environment) as arguments, so the checks can be unit-tested without touching
the real system.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from code_factory.config import Settings

MIN_PYTHON = (3, 12)
COMMAND_TIMEOUT_S = 30.0


class Status(StrEnum):
    """Outcome of a single check."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one doctor check.

    Attributes:
        name: Short name of what was checked.
        status: Whether the check passed, warned or failed.
        detail: Human-readable explanation.
        required: Whether a failure of this check should fail `cf doctor`.
    """

    name: str
    status: Status
    detail: str
    required: bool = True

    @property
    def blocking(self) -> bool:
        """True if this result should make `cf doctor` exit non-zero."""
        return self.required and self.status is Status.FAIL


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of running an external command.

    Attributes:
        returncode: Process exit code (127 if the command could not be started).
        stdout: Captured standard output.
        stderr: Captured standard error.
    """

    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str]], CommandResult]
Which = Callable[[str], str | None]


def run_command(args: Sequence[str]) -> CommandResult:
    """Run a command and capture its output, never raising for a missing binary or timeout.

    Args:
        args: The command and its arguments.

    Returns:
        The exit code and captured output.
    """
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(returncode=127, stderr=str(exc))
    except subprocess.TimeoutExpired:
        return CommandResult(returncode=124, stderr=f"timed out after {COMMAND_TIMEOUT_S:.0f}s")
    return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def check_python(version: tuple[int, int] | None = None) -> CheckResult:
    """Check that the running Python is new enough.

    Args:
        version: The (major, minor) version to check; defaults to the running interpreter.

    Returns:
        The check result.
    """
    current = version if version is not None else (sys.version_info.major, sys.version_info.minor)
    label = f"{current[0]}.{current[1]}"
    if current >= MIN_PYTHON:
        return CheckResult("python", Status.OK, label)
    needed = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    return CheckResult("python", Status.FAIL, f"{label} found, {needed}+ required")


def check_git(which: Which) -> CheckResult:
    """Check that `git` is on the PATH.

    Args:
        which: Lookup returning the path of an executable, or None.

    Returns:
        The check result.
    """
    path = which("git")
    if path is None:
        return CheckResult("git", Status.FAIL, "git not found on PATH")
    return CheckResult("git", Status.OK, path)


def check_gh(which: Which, run: Runner) -> CheckResult:
    """Check that the GitHub CLI is installed and logged in.

    Args:
        which: Lookup returning the path of an executable, or None.
        run: Command runner.

    Returns:
        The check result.
    """
    if which("gh") is None:
        return CheckResult("gh", Status.FAIL, "gh not found on PATH")
    result = run(["gh", "auth", "status"])
    if result.returncode != 0:
        return CheckResult("gh", Status.FAIL, "gh is not logged in (run `gh auth login`)")
    return CheckResult("gh", Status.OK, "logged in")


def parse_claude_auth(output: str) -> tuple[bool, str]:
    """Parse the JSON printed by `claude auth status`.

    Only non-identifying fields are kept, so the account email never reaches the output.

    Args:
        output: Standard output of `claude auth status`.

    Returns:
        A (logged_in, description) pair. Unparseable output counts as not logged in.
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False, "could not parse `claude auth status` output"
    if not isinstance(data, dict):
        return False, "unexpected `claude auth status` output"
    info: dict[str, object] = data  # pyright: ignore[reportUnknownVariableType]
    if info.get("loggedIn") is not True:
        return False, "not logged in (run `claude auth login`)"
    method = str(info.get("authMethod", "unknown"))
    plan = info.get("subscriptionType")
    return True, f"logged in via {method}" + (f" ({plan})" if plan else "")


def check_claude(which: Which, run: Runner) -> CheckResult:
    """Check that the Claude CLI is installed and logged in.

    Args:
        which: Lookup returning the path of an executable, or None.
        run: Command runner.

    Returns:
        The check result.
    """
    if which("claude") is None:
        return CheckResult("claude", Status.FAIL, "claude CLI not found on PATH")
    result = run(["claude", "auth", "status"])
    logged_in, detail = parse_claude_auth(result.stdout)
    if result.returncode != 0 or not logged_in:
        return CheckResult("claude", Status.FAIL, detail)
    return CheckResult("claude", Status.OK, detail)


def check_api_key(env: Mapping[str, str], allow_api_key: bool) -> CheckResult:
    """Check that `ANTHROPIC_API_KEY` is not set, since it would switch billing to the API.

    Args:
        env: The environment to inspect.
        allow_api_key: Whether the user explicitly allowed API-key billing.

    Returns:
        The check result.
    """
    name = "ANTHROPIC_API_KEY"
    if not env.get("ANTHROPIC_API_KEY"):
        return CheckResult(name, Status.OK, "not set (Claude login is used)")
    if allow_api_key:
        return CheckResult(
            name, Status.WARN, "SET: usage is billed to the API (allowed by CF_ALLOW_API_KEY)"
        )
    return CheckResult(
        name,
        Status.FAIL,
        "SET: this silently switches billing to the API. Unset it, "
        "or set CF_ALLOW_API_KEY=true to allow it.",
    )


def list_profiles(agents_dir: Path) -> list[str]:
    """List the role profile names (`<role>.md`) in the agents directory.

    Args:
        agents_dir: Directory holding the role profiles.

    Returns:
        Sorted profile names without the `.md` suffix.
    """
    return sorted(p.stem for p in agents_dir.glob("*.md") if p.is_file())


def list_skills(skills_dir: Path) -> list[str]:
    """List the skills (`<skill>/SKILL.md`) in the skills directory.

    Args:
        skills_dir: Directory holding the skills library.

    Returns:
        Sorted skill names.
    """
    return sorted(p.parent.name for p in skills_dir.glob("*/SKILL.md") if p.is_file())


def _check_listing(name: str, directory: Path, items: Callable[[Path], list[str]]) -> CheckResult:
    """Check that a directory exists and contains at least one item."""
    if not directory.is_dir():
        return CheckResult(name, Status.FAIL, f"{directory} does not exist")
    found = items(directory)
    if not found:
        return CheckResult(name, Status.FAIL, f"{directory} contains none")
    return CheckResult(name, Status.OK, f"{directory}: {', '.join(found)}")


def check_agents_dir(agents_dir: Path) -> CheckResult:
    """Check that the agents directory exists and holds role profiles.

    Args:
        agents_dir: Directory holding the role profiles.

    Returns:
        The check result, listing the profile names.
    """
    return _check_listing("agents_dir", agents_dir, list_profiles)


def check_skills_dir(skills_dir: Path) -> CheckResult:
    """Check that the skills directory exists and holds skills.

    Args:
        skills_dir: Directory holding the skills library.

    Returns:
        The check result, listing the skill names.
    """
    return _check_listing("skills_dir", skills_dir, list_skills)


def check_msmtp(which: Which) -> CheckResult:
    """Check whether msmtp is installed (optional: only needed for email notifications).

    Args:
        which: Lookup returning the path of an executable, or None.

    Returns:
        The check result; never blocking.
    """
    path = which("msmtp")
    if path is None:
        return CheckResult(
            "msmtp", Status.WARN, "not found: email notifications disabled", required=False
        )
    return CheckResult("msmtp", Status.OK, path, required=False)


def run_checks(
    settings: Settings,
    *,
    run: Runner = run_command,
    which: Which = shutil.which,
    env: Mapping[str, str] | None = None,
    python_version: tuple[int, int] | None = None,
) -> list[CheckResult]:
    """Run every doctor check.

    Args:
        settings: The effective settings.
        run: Command runner (injectable for tests).
        which: Executable lookup (injectable for tests).
        env: Environment to inspect; defaults to `os.environ`.
        python_version: Python version to check; defaults to the running interpreter.

    Returns:
        One result per check, in display order.
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    return [
        check_python(python_version),
        check_git(which),
        check_gh(which, run),
        check_claude(which, run),
        check_api_key(environ, settings.allow_api_key),
        check_agents_dir(settings.agents_dir),
        check_skills_dir(settings.skills_dir),
        check_msmtp(which),
    ]


def has_blocking_failure(results: Sequence[CheckResult]) -> bool:
    """Tell whether any required check failed.

    Args:
        results: Results from `run_checks`.

    Returns:
        True if `cf doctor` should exit non-zero.
    """
    return any(r.blocking for r in results)
