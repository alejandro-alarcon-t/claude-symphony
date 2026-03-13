"""Tests for config.py — SPEC 17.1 Config Parsing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_symphony.config import (
    ClaudeConfig,
    HooksConfig,
    LinearStatesConfig,
    ServiceConfig,
    StateConfig,
    TrackerConfig,
    WorkspaceConfig,
    _coerce_int,
    _coerce_list,
    _parse_hooks,
    _parse_state_config,
    _resolve_env,
    _resolve_linear_state_name,
    merge_state_config,
    parse_workflow_file,
    validate_config,
)


# ── Helper functions ─────────────────────────────────────────────────────────


class TestResolveEnv:
    def test_literal_value(self):
        assert _resolve_env("literal") == "literal"

    def test_env_var_found(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "secret")
        assert _resolve_env("$MY_VAR") == "secret"

    def test_env_var_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert _resolve_env("$MISSING_VAR") == ""

    def test_non_string_passthrough(self):
        assert _resolve_env(42) == 42  # type: ignore


class TestCoerceInt:
    def test_none_returns_default(self):
        assert _coerce_int(None, 10) == 10

    def test_valid_int(self):
        assert _coerce_int(5, 10) == 5

    def test_valid_string_int(self):
        assert _coerce_int("42", 10) == 42

    def test_invalid_returns_default(self):
        assert _coerce_int("abc", 10) == 10

    def test_float_coerced(self):
        assert _coerce_int(3.7, 10) == 3


class TestCoerceList:
    def test_list_passthrough(self):
        assert _coerce_list(["a", "b"]) == ["a", "b"]

    def test_comma_separated_string(self):
        assert _coerce_list("a, b, c") == ["a", "b", "c"]

    def test_empty_string(self):
        assert _coerce_list("") == []

    def test_non_string_non_list(self):
        assert _coerce_list(42) == []

    def test_list_of_ints(self):
        assert _coerce_list([1, 2]) == ["1", "2"]


class TestParseHooks:
    def test_none_input(self):
        assert _parse_hooks(None) is None

    def test_empty_dict(self):
        assert _parse_hooks({}) is None

    def test_with_values(self):
        result = _parse_hooks({
            "after_create": "echo hi",
            "timeout_ms": 5000,
        })
        assert result is not None
        assert result.after_create == "echo hi"
        assert result.timeout_ms == 5000
        assert result.before_remove is None


class TestParseStateConfig:
    def test_minimal(self):
        sc = _parse_state_config("test", {})
        assert sc.name == "test"
        assert sc.type == "agent"
        assert sc.runner == "claude"
        assert sc.session == "inherit"
        assert sc.transitions == {}

    def test_full(self):
        sc = _parse_state_config("impl", {
            "type": "agent",
            "prompt": "prompts/impl.md",
            "linear_state": "active",
            "runner": "codex",
            "model": "opus",
            "max_turns": 15,
            "transitions": {"complete": "done"},
        })
        assert sc.runner == "codex"
        assert sc.model == "opus"
        assert sc.max_turns == 15
        assert sc.transitions == {"complete": "done"}

    def test_gate_config(self):
        sc = _parse_state_config("gate", {
            "type": "gate",
            "rework_to": "investigate",
            "max_rework": 3,
            "transitions": {"approve": "implement"},
        })
        assert sc.type == "gate"
        assert sc.rework_to == "investigate"
        assert sc.max_rework == 3


class TestResolveLinearStateName:
    def test_known_keys(self):
        ls = LinearStatesConfig(active="Working", review="Reviewing")
        assert _resolve_linear_state_name("active", ls) == "Working"
        assert _resolve_linear_state_name("review", ls) == "Reviewing"

    def test_unknown_key_passthrough(self):
        ls = LinearStatesConfig()
        assert _resolve_linear_state_name("custom", ls) == "custom"


# ── ServiceConfig ─────────────────────────────────────────────────────────────


class TestServiceConfig:
    def test_resolved_api_key_literal(self):
        cfg = ServiceConfig(tracker=TrackerConfig(api_key="literal-key"))
        assert cfg.resolved_api_key() == "literal-key"

    def test_resolved_api_key_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env-value")
        cfg = ServiceConfig(tracker=TrackerConfig(api_key="$MY_KEY"))
        assert cfg.resolved_api_key() == "env-value"

    def test_resolved_api_key_fallback(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "fallback-key")
        cfg = ServiceConfig(tracker=TrackerConfig(api_key=""))
        assert cfg.resolved_api_key() == "fallback-key"

    def test_resolved_api_key_no_key(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        cfg = ServiceConfig(tracker=TrackerConfig(api_key=""))
        assert cfg.resolved_api_key() == ""

    def test_entry_state(self, sample_service_config):
        assert sample_service_config.entry_state == "investigate"

    def test_entry_state_no_agents(self):
        cfg = ServiceConfig(states={
            "done": StateConfig(name="done", type="terminal"),
        })
        assert cfg.entry_state is None

    def test_active_linear_states(self, sample_service_config):
        states = sample_service_config.active_linear_states()
        assert "In Progress" in states

    def test_gate_linear_states(self, sample_service_config):
        states = sample_service_config.gate_linear_states()
        assert "Human Review" in states

    def test_terminal_linear_states(self, sample_service_config):
        states = sample_service_config.terminal_linear_states()
        assert "Done" in states
        assert "Closed" in states


# ── WorkspaceConfig ───────────────────────────────────────────────────────────


class TestWorkspaceConfig:
    def test_resolved_root_default(self):
        cfg = WorkspaceConfig(root="")
        result = cfg.resolved_root()
        assert "claude_symphony_workspaces" in str(result)

    def test_resolved_root_tilde(self, monkeypatch):
        monkeypatch.setenv("HOME", "/home/testuser")
        cfg = WorkspaceConfig(root="~/workspaces")
        result = cfg.resolved_root()
        assert str(result).startswith("/home/testuser")

    def test_resolved_root_env_var(self, monkeypatch):
        monkeypatch.setenv("WS_ROOT", "/custom/path")
        cfg = WorkspaceConfig(root="$WS_ROOT/agents")
        result = cfg.resolved_root()
        assert str(result) == "/custom/path/agents"

    def test_resolved_repo_none(self):
        cfg = WorkspaceConfig(repo="")
        assert cfg.resolved_repo() is None

    def test_resolved_repo_with_value(self):
        cfg = WorkspaceConfig(repo="/some/repo")
        assert cfg.resolved_repo() is not None


# ── parse_workflow_file ───────────────────────────────────────────────────────


class TestParseWorkflowFile:
    def test_yaml_format(self, workflow_yaml):
        result = parse_workflow_file(workflow_yaml)
        assert result.config.tracker.team_key == "FIC"
        assert result.config.claude.max_turns == 10
        assert "investigate" in result.config.states
        assert "done" in result.config.states

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_workflow_file(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("[not a mapping")
        with pytest.raises(Exception):
            parse_workflow_file(bad)

    def test_non_mapping_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("- list\n- item\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            parse_workflow_file(bad)

    def test_md_format_with_frontmatter(self, tmp_path):
        md = tmp_path / "workflow.md"
        md.write_text(
            "---\n"
            "tracker:\n"
            "  api_key: md-key\n"
            "  team_key: TEST\n"
            "states:\n"
            "  work:\n"
            "    type: agent\n"
            "    linear_state: active\n"
            "  done:\n"
            "    type: terminal\n"
            "    linear_state: terminal\n"
            "---\n"
            "This is the prompt body\n"
        )
        result = parse_workflow_file(md)
        assert result.config.tracker.api_key == "md-key"
        assert result.prompt_template == "This is the prompt body"

    def test_yaml_format_no_prompt_template(self, workflow_yaml):
        result = parse_workflow_file(workflow_yaml)
        assert result.prompt_template == ""

    def test_defaults_applied(self, tmp_path):
        minimal = tmp_path / "min.yaml"
        minimal.write_text("tracker:\n  api_key: k\n")
        result = parse_workflow_file(minimal)
        assert result.config.polling.interval_ms == 30_000
        assert result.config.claude.command == "claude"
        assert result.config.claude.max_turns == 20
        assert result.config.workspace.mode == "clone"

    def test_state_parsing(self, workflow_yaml):
        result = parse_workflow_file(workflow_yaml)
        inv = result.config.states["investigate"]
        assert inv.type == "agent"
        assert inv.prompt == "prompts/investigate.md"
        assert inv.transitions == {"complete": "done"}


# ── merge_state_config ────────────────────────────────────────────────────────


class TestMergeStateConfig:
    def test_no_overrides(self):
        state = StateConfig(name="s")
        root_claude = ClaudeConfig(model="sonnet", max_turns=10)
        root_hooks = HooksConfig(after_create="echo hi")
        claude, hooks = merge_state_config(state, root_claude, root_hooks)
        assert claude.model == "sonnet"
        assert claude.max_turns == 10
        assert hooks.after_create == "echo hi"

    def test_state_overrides_model(self):
        state = StateConfig(name="s", model="opus")
        root_claude = ClaudeConfig(model="sonnet")
        claude, _ = merge_state_config(state, root_claude, HooksConfig())
        assert claude.model == "opus"

    def test_state_overrides_max_turns(self):
        state = StateConfig(name="s", max_turns=3)
        root_claude = ClaudeConfig(max_turns=20)
        claude, _ = merge_state_config(state, root_claude, HooksConfig())
        assert claude.max_turns == 3

    def test_state_overrides_hooks(self):
        state_hooks = HooksConfig(after_create="state hook")
        state = StateConfig(name="s", hooks=state_hooks)
        root_hooks = HooksConfig(after_create="root hook")
        _, hooks = merge_state_config(state, ClaudeConfig(), root_hooks)
        assert hooks.after_create == "state hook"

    def test_state_overrides_permission_mode(self):
        state = StateConfig(name="s", permission_mode="allowedTools")
        root_claude = ClaudeConfig(permission_mode="auto")
        claude, _ = merge_state_config(state, root_claude, HooksConfig())
        assert claude.permission_mode == "allowedTools"

    def test_state_overrides_allowed_tools(self):
        state = StateConfig(name="s", allowed_tools=["Bash"])
        root_claude = ClaudeConfig(allowed_tools=["Bash", "Read", "Edit"])
        claude, _ = merge_state_config(state, root_claude, HooksConfig())
        assert claude.allowed_tools == ["Bash"]


# ── validate_config ──────────────────────────────────────────────────────────


class TestValidateConfig:
    def test_valid_config(self, sample_service_config):
        errors = validate_config(sample_service_config)
        assert errors == []

    def test_no_states(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={},
        )
        errors = validate_config(cfg)
        assert any("No states" in e for e in errors)

    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="", team_key="T"),
            states={"s": StateConfig(name="s", type="agent", prompt="p.md"),
                    "d": StateConfig(name="d", type="terminal")},
        )
        errors = validate_config(cfg)
        assert any("API key" in e for e in errors)

    def test_missing_project_and_team(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", project_slug="", team_key=""),
            states={"s": StateConfig(name="s", type="agent", prompt="p.md"),
                    "d": StateConfig(name="d", type="terminal")},
        )
        errors = validate_config(cfg)
        assert any("project_slug" in e for e in errors)

    def test_invalid_state_type(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={"s": StateConfig(name="s", type="invalid")},
        )
        errors = validate_config(cfg)
        assert any("invalid type" in e for e in errors)

    def test_gate_missing_rework_to(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={
                "g": StateConfig(
                    name="g", type="gate",
                    transitions={"approve": "done"},
                ),
                "done": StateConfig(name="done", type="terminal"),
                "s": StateConfig(name="s", type="agent", prompt="p.md"),
            },
        )
        errors = validate_config(cfg)
        assert any("rework_to" in e for e in errors)

    def test_gate_missing_approve_transition(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={
                "g": StateConfig(
                    name="g", type="gate", rework_to="s",
                    transitions={},
                ),
                "s": StateConfig(name="s", type="agent", prompt="p.md"),
                "done": StateConfig(name="done", type="terminal"),
            },
        )
        errors = validate_config(cfg)
        assert any("approve" in e for e in errors)

    def test_transition_to_unknown_state(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={
                "s": StateConfig(
                    name="s", type="agent", prompt="p.md",
                    transitions={"complete": "nonexistent"},
                ),
                "done": StateConfig(name="done", type="terminal"),
            },
        )
        errors = validate_config(cfg)
        assert any("nonexistent" in e for e in errors)

    def test_no_agent_states(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={"done": StateConfig(name="done", type="terminal")},
        )
        errors = validate_config(cfg)
        assert any("No agent" in e for e in errors)

    def test_no_terminal_states(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={"s": StateConfig(name="s", type="agent", prompt="p.md")},
        )
        errors = validate_config(cfg)
        assert any("No terminal" in e for e in errors)

    def test_agent_missing_prompt(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={
                "s": StateConfig(name="s", type="agent"),
                "done": StateConfig(name="done", type="terminal"),
            },
        )
        errors = validate_config(cfg)
        assert any("prompt" in e for e in errors)

    def test_invalid_linear_state_key(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={
                "s": StateConfig(
                    name="s", type="agent", prompt="p.md",
                    linear_state="bogus",
                ),
                "done": StateConfig(name="done", type="terminal"),
            },
        )
        errors = validate_config(cfg)
        assert any("bogus" in e for e in errors)

    def test_gate_rework_to_unknown_state(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T"),
            states={
                "g": StateConfig(
                    name="g", type="gate", rework_to="missing",
                    transitions={"approve": "done"},
                ),
                "s": StateConfig(name="s", type="agent", prompt="p.md"),
                "done": StateConfig(name="done", type="terminal"),
            },
        )
        errors = validate_config(cfg)
        assert any("missing" in e for e in errors)

    def test_unsupported_tracker_kind(self):
        cfg = ServiceConfig(
            tracker=TrackerConfig(api_key="k", team_key="T", kind="jira"),
            states={
                "s": StateConfig(name="s", type="agent", prompt="p.md"),
                "done": StateConfig(name="done", type="terminal"),
            },
        )
        errors = validate_config(cfg)
        assert any("jira" in e for e in errors)
