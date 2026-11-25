# code-factory

A LangGraph-based harness for Claude coding agents. It takes a task through plan, code, test, review and a pull request, and records every step in a local event store that a CLI, an HTTP API and a future dashboard can read.

**Status: early development.** See [docs/plan.md](docs/plan.md) for the design and milestones.

The agent instructions it uses live in a separate repo, [mochkai/agents](https://github.com/mochkai/agents), and skills come from [mochkai/skills](https://github.com/mochkai/skills).
