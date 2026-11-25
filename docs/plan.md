# code-factory: design plan

Status: approved 2026-11-25 (v1). It was revised after a design review, and milestones may still be refined in their PRs.

## Purpose
code-factory replaces the earlier bash/JS "agent farm" with a proper Python project. It runs a coding task end-to-end (plan → code → test → review → pull request) with Claude coding agents, and records every step in a local store so you can **see and steer** what is happening through a CLI and an HTTP API. A dashboard will come later.

code-factory only runs when you start it, either on one task (`cf run <id>`) or as a worker you launch. There is no unattended scheduling such as cron.

## Constraints
- **Claude access:** the Claude Agent SDK (Python), using your own Claude Pro login, for personal, individual use only. The API is never exposed beyond loopback, and the login is never shared. If `ANTHROPIC_API_KEY` is set, it would silently switch billing to the API, so code-factory refuses to run until it is unset or explicitly allowed.
- **Usage limits** are shared with your interactive work. Concurrency defaults to 1 (max 2), and usage is checked before every agent step.
- **Machine:** WSL, about 7 GB RAM. Repos under `/mnt/c` are rejected.
- **Agent instructions** come from `~/agents/agents/*.md` (role profiles) and `~/skills/*/SKILL.md`. code-factory appends its own per-role contract, which wins on conflict.

## Stack
Python 3.12+, uv, `langgraph` 1.2.x with `langgraph-checkpoint-sqlite` (AsyncSqliteSaver), `claude-agent-sdk` 0.2.x, FastAPI + uvicorn, typer, pydantic v2 + pydantic-settings, stdlib `sqlite3` (WAL, `PRAGMA user_version` migrations), httpx, ruff, pyright (strict), pytest + pytest-asyncio.

Git is driven via subprocess (worktrees). GitHub is driven via the `gh` CLI, using REST for edits and labels because `gh pr edit` fails on this account. Email uses msmtp, with settings in `.env`, which is git-ignored. CI runs on GitHub Actions: lint, types and tests, with no LLM calls.

## Architecture
```
src/code_factory/
  config.py         settings (.env + env vars): paths, db files, concurrency, per-role model, usage limits,
                    notification settings, API token
  profiles.py       load ~/agents/agents/<role>.md (frontmatter + body) + code-factory role contract;
                    `cf profiles check` flags leftover farm-only text; profile sha256 logged per run
  runners/
    base.py         AgentRunner protocol (agentic, cwd-bound) and StructuredLLM protocol (messages + schema)
    agent_sdk.py    claude-agent-sdk: explicit setting_sources, Agent/Task tool disabled, add_dirs=[~/skills],
                    max_turns + timeout per role, can_use_tool guard (no writes outside the worktree, no push/gh),
                    structured output (SDK json schema, else fenced JSON + one repair turn), RateLimitEvent capture,
                    session resume, auth preflight, kill the process tree on cancel
    replay.py       replays recorded real transcripts for tests (no quota)
  graph/
    state.py        small state: spec, plan, base/node-start shas, session ids per role, test + review results,
                    round, pr_url, outcome (success | wip | failed)
    nodes.py        prepare_worktree, plan, code (one coder chosen by task type), test (deterministic: the repo's
                    lint/type/test commands, no LLM), review, commit, open_pr (idempotent; draft when not passing)
    build.py        linear graph with a ≤2-round code↔test/review loop; durability="sync"; explicit recursion_limit
  store/            factory.db: tasks (lifecycle status, owned by the worker), events (append-only, autoincrement
                    id), commands (cancel/resume rows written by the API, read by the worker), usage snapshots.
                    Checkpoints live in a separate checkpoints.db.
  usage.py          usage gate from RateLimitEvent (+ cached probe); a limit or auth loss → task "paused", never failed
  worker.py         separate process: queue, concurrency, per-node usage gate, resume after restart, cancel,
                    orphan-process and worktree cleanup
  git_ops.py        worktrees/branches under the data dir; never touches your own checkout
  github.py         PR create/comment/labels (stacked-PR note rule)
  notify.py         email via msmtp: READY / NEEDS_HUMAN (same behaviour as the old farm)
  redact.py         strips secrets/env values from events and PR bodies; repo content + PR comments are untrusted
  api/app.py        separate process, 127.0.0.1 only + bearer token: tasks, events (SSE via Last-Event-ID),
                    commands, /status, /health
  cli.py            `cf`: add, list, show, logs [-f], run, cancel, worker, api, usage, profiles check, run-role
```

## Milestones (one PR each, reviewed by the reviewer agent, merged by you)
- **M0 Scaffold:** uv project, ruff, pyright, pytest, CI, `config.py`, `.env.example`, README, changelog.md, CLAUDE.md.
- **M1 Runner spike:**
  - AgentRunner + AgentSDKRunner, record/replay runner, and `cf run-role <role> <dir> "<prompt>"`.
  - Verify against the real SDK: structured output, RateLimitEvent, session resume, auth preflight, peak memory and kill-on-cancel.
  - Profile loader + role contracts.
- **M2 Store + git:** tasks/events/commands (WAL), worktrees, `cf add/list/show/logs`.
- **M3 Linear graph, foreground:** prepare → plan → code → test → review → loop (≤2) → commit → PR (draft if not passing), checkpointed, `cf run <id>`. **First real end-to-end run on a demo repo.**
- **M4 Worker:** daemon, queue, usage gate per node, pause/resume on limits or auth loss, restart resume, cancel, cleanup.
- **M5 API:** FastAPI on loopback with a token, SSE from events, `/status`.
- **M6 After the PR:** project-manager decision, fix rounds on the same PR, docs step, email notifications.
- **Later:** coder fan-out (one worktree per step), approval interrupts, StructuredLLM backends (ChatAnthropic / Ollama per role), Linear/Postgres store, dashboard.

## Testing without burning quota
- Unit and graph tests use the replay runner with **recorded** transcripts captured in M1.
- Real-SDK tests are marked `@pytest.mark.live` (Haiku, a tiny fixture repo, low `max_turns`), opt-in only, and never run in CI.
