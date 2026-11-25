# code-factory

A LangGraph-based harness that runs coding agents (Claude and Codex) in isolated sandbox containers. It takes a task from a GitHub issue through plan, code, test, review and a pull request, and records every step in a Postgres event store that a CLI, an HTTP API and a future dashboard can read. It runs with docker compose locally and deploys unchanged to a cloud VM.

**Status: early development.** See [docs/plan.md](docs/plan.md) for the design and milestones.

The agent instructions it uses live in a separate repo, [mochkai/agents](https://github.com/mochkai/agents), and skills come from [mochkai/skills](https://github.com/mochkai/skills).
