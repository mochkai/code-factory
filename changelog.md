# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Design plan v2 (`docs/plan.md`): container-first architecture with one hardened sandbox per agent step, a sandbox launcher, an egress allow-list proxy and read-only package mirrors; Claude (Pro) and Codex (ChatGPT Go) runners; Postgres store; switchable on-demand/autonomous mode; every task tied to a GitHub issue, with worker-created `<type>/<issue#>-<slug>` branches and push-only-to-own-branches ownership; milestones re-cut (M1a subscription check first).
