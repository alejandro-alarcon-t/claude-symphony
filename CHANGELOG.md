# Changelog

All notable changes to Claude Symphony are documented here.

---

## [0.2.0] - 2026-03-13

### Added

- `claude-symphony init [path]` scaffolds `workflow.yaml` + `prompts/`
- Git worktree workspace mode (`workspace.mode: worktree`)
- Parent/epic context in Linear queries (`Issue.parent`, `Issue.siblings`)
- Team key filtering (`tracker.team_key`) as alternative to project slug
- `IssueRef` model for parent/sibling references

### Changed

- Renamed from Stokowski to Claude Symphony (v0.2.0)
- Permission mode: `--permission-mode auto`
- Tracking markers: `claude-symphony:state` / `claude-symphony:gate`
- `ensure_workspace()`/`remove_workspace()` accept `WorkspaceConfig`

---

## [0.1.0] - 2026-03-08

### Added

- Async orchestration loop polling Linear for issues in configurable states
- Per-issue isolated git workspace lifecycle with `after_create`, `before_run`, `after_run`, `before_remove` hooks
- Claude Code CLI integration with `--output-format stream-json` streaming and multi-turn `--resume` sessions
- Exponential backoff retry and stall detection
- State reconciliation — running agents cancelled when Linear issue moves to terminal state
- Optional FastAPI web dashboard with live agent status
- Rich terminal UI with persistent status bar and single-key controls
- Jinja2 prompt templates with full issue context
- `.env` auto-load and `$VAR` env references in config
- Hot-reload of `WORKFLOW.md` on every poll tick
- Per-state concurrency limits
- `--dry-run` mode for config validation without dispatching agents
- Startup update check with footer indicator
- `last_run_at` template variable injected into agent prompts for rework timestamp filtering
- Append-only Linear comment strategy (planning + completion comment per run)

---

[Unreleased]: https://github.com/alejandro-alarcon-t/claude-symphony/compare/v0.2.0...HEAD
[0.1.0]: https://github.com/alejandro-alarcon-t/claude-symphony/releases/tag/v0.1.0
[0.2.0]: https://github.com/alejandro-alarcon-t/claude-symphony/compare/v0.1.0...v0.2.0
