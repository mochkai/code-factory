# code-factory: design plan

Status: v2, approved 2026-11-25. It replaces the v1 laptop-only plan with a container-first design. Milestones may still be refined in their PRs.

## Purpose
code-factory runs coding tasks end to end: plan, code, test, review, then a pull request. It uses LLM coding agents, and every agent step runs in its own sandbox container. You can see and steer it through a CLI and an HTTP API, and later a dashboard. It starts locally with docker compose, then moves unchanged to a cloud VM, and to Kubernetes after that.

## Decisions
- **Run mode:** switchable. In on-demand mode it only runs tasks you start yourself. In autonomous mode it works through the queue on its own.
- **Where it runs:** Docker compose locally first. Later a cloud VM or Kubernetes, using the same images.
- **Providers:**
  - Claude, through your Pro subscription.
  - Codex, through ChatGPT Go. It can act as reviewer or second opinion, as an alternative coder, or as the fallback when Claude hits its usage limits.
- **Task source:** its own queue only, fed by the CLI, the API or the dashboard. Picking up GitHub issues and PR comments comes later.
- **Store:** Postgres. LangGraph checkpoints use PostgresSaver.
- **Repos:** GitHub only. Sandboxes never get GitHub access or credentials.

## Architecture
```
compose:
  postgres         tasks, events, commands, usage windows (per provider, per 5h), checkpoints
  api              FastAPI + token auth, SSE; writes commands; no Docker access
  worker           LangGraph; owns task status; GitHub App token + SMTP secret; clones repos,
                   validates and pushes patches; asks the launcher for sandboxes
  sandbox-launcher only service with the Docker socket; accepts {role, image digest, workspace id,
                   limits} and applies a fixed, hardened HostConfig (no caller mounts/caps/network)
  egress-proxy     allow-list: Anthropic + OpenAI endpoints and the package mirrors only
  pypi/npm mirror  read-only pull-through caches (devpi, verdaccio): no publishing possible
  sandbox (per step, ephemeral)
```

### Sandbox
- **Image:** pinned by digest, including the base image, the claude CLI, the Agent SDK, the codex CLI, and agents/ and skills/ at locked commits. Renovate opens PRs to bump them. Every task records the image digest and the skills commit it ran with.
- **Hardening:**
  - non-root, cap-drop ALL, no-new-privileges, read-only rootfs;
  - HOME on a small tmpfs, and the workspace on a per-task disk volume, not RAM;
  - mem, cpu and pids limits plus a timeout;
  - gVisor when native dockerd is in use;
  - telemetry and auto-update turned off (`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_AUTOUPDATER`, the codex equivalents);
  - DNS kept from becoming an escape route.
- **In:** the task spec, the role, the provider and model, the workspace volume (seeded from a bundle the worker made of the base ref), and the credential for that one provider. For resumed steps, the previous Claude session file.
- **Out:** a result JSON checked against a schema, a diff (not commits), the transcript, usage events, and the session file.
- **Test steps** run in two phases with no LLM credentials:
  1. A setup sandbox that can reach only the package mirrors.
  2. A test sandbox with no network at all (`network=none`).

### Worker safety
- **Cloning:** short-lived GitHub App tokens passed through GIT_ASKPASS. No hooks, no LFS smudge, no submodules, and `protocol.file.allow=never`.
- **Checking the diff before pushing:**
  - Reject symlinks, gitlinks, mode changes, and edits to `.github/**`, `.gitattributes` and `.gitmodules`.
  - Enforce path and size limits.
  - Scan the diff, commit message and branch name for exact secret values and gitleaks rules.
- **Committing and pushing:** the worker applies the diff to its own clean clone and commits under its own identity. It pushes only to branches it owns (see below). The GitHub App has no `workflow` permission.
- **Untrusted input:** repo content, PR text and LLM output are all treated as untrusted. Secrets are redacted from events and PR bodies.

### Issues, branches and ownership
- **Every task has a GitHub issue.** Either the task names one ("work on issue 123"), or the first step is the **project-manager** agent (intake mode) drafting one: title, description with acceptance criteria, type (feat, fix, docs, refactor, test, perf, ci, build, chore) and coder role. The worker creates it through the API. A named issue is only accepted if it was opened by the user or the code-factory App, in an allow-listed repo.
- **The worker creates the branch** (plain code, not an LLM) right after the issue exists: `<type>/<issue#>-<slug>`, e.g. `feat/123-user-login`, with no agent-identifying prefix. Commits and PR titles use the same Conventional Commits type, and the PR body says `Closes #123`. The assigned role is stored on the task (optionally also as an issue label).
- **Ownership:** when it creates the branch, the worker records task, issue, branch and base commit. It only ever pushes to branches it created for that task, never to another task's branch, a human's branch, the default branch or a protected branch. If the branch name already exists and isn't recorded as its own, the task stops and asks.
- **Humans may push to agent branches.** Before each step the worker fast-forwards to pick up their commits and builds on top. It never force-pushes. All roles in a task share its branch; future parallel coders get sub-branches. A GitHub ruleset on `main` is the backstop.

### Runners
- **ClaudeRunner:** the Agent SDK, authenticated with `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`.
- **CodexRunner:** `codex exec --output-schema`. The worker owns `auth.json`:
  - It refreshes the token under a lock and writes it back after the step.
  - Only one Codex sandbox runs at a time.
  - If Codex accepts an access-only token, the refresh token is stripped before the file enters the sandbox.
- **ReplayRunner:** plays back recorded transcripts for tests.
- **Provider choice:** each role has an ordered list of providers to fall back through. A usage gate checks every provider before any step is scheduled. Hitting a limit triggers a fallback or a pause, never a failure.

### Config and notifications
- **Config:** env vars plus `*_FILE` secret files, with no paths specific to your machine. `cf doctor` works inside the containers.
- **Email:** sent with smtplib using your Gmail app password, from "Agent Farm", for READY and NEEDS_HUMAN.

## Milestones (one PR each, except M1a)
- **M1a Check the subscriptions (no PR, about a day).**
  - Confirm that the Anthropic and ChatGPT Go terms allow this.
  - Run a hardened `docker run` by hand with claude and with codex behind the proxy. Note memory use and how auth behaves.
- **M0 Scaffold:** uv, ruff, pyright, pytest and CI; env-only config with secret files; the worker/api Dockerfile and a compose file with postgres; `cf version`, `cf config` and `cf doctor`.
- **M1b Sandbox:** the launcher, egress proxy and mirrors; the sandbox image and lock file; the sandbox in/out contract; ClaudeRunner on a fixture repo; recorded transcripts.
- **M1c Codex:** CodexRunner, the auth.json broker, and its own recordings.
- **M2 Foreground graph:** issue intake (fetched, or drafted by the project manager), branch, clone, bundle, plan, code, test, review, up to 2 loops, validate, push, PR. It uses an in-memory checkpointer and gives the first real end-to-end run.
- **M3 Store:** the Postgres schema and migrations, PostgresSaver, and `cf add`, `cf list`, `cf show` and `cf logs`.
- **M4 Worker:** the on-demand/autonomous switch, the queue, the usage gates and fallback, pause, resume, cancel, resume after a restart, and cleanup.
- **M5 API:** token auth, SSE and `/status`. It is published to localhost only by default.
- **M6 After the PR:** the project-manager decision, fix rounds, the docs step and email.
- **M7 Deploy:** a cloud VM guide (compose, a TLS reverse proxy, secrets, backups).
- **Later:** a Kubernetes Job backend, the dashboard, GitHub issue and PR-comment sources, fan-out, and approval interrupts.

## Limits on your laptop
In WSL with 7 GB of RAM, run one sandbox at a time, capped at about 2 GB. Set the WSL memory in `.wslconfig`. gVisor is optional.

## Open risks
- **Anthropic policy:** Anthropic's rules on using a Pro subscription with the SDK changed in 2026, and the sources conflict. M1a settles this. The runner interface keeps an API-key path open.
- **Codex on Go:** ChatGPT Go may include Codex only in the desktop app. M1a checks this; the fallback is an OpenAI API key.
- **Token theft:** a prompt injection could steal the LLM token from inside a sandbox. The egress allow-list limits where it can send it.
