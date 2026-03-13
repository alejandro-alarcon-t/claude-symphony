"""Tests for prompt.py — three-layer prompt assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_symphony.config import LinearStatesConfig, ServiceConfig, StateConfig, PromptsConfig
from claude_symphony.models import Issue
from claude_symphony.prompt import (
    _SilentUndefined,
    assemble_prompt,
    build_lifecycle_section,
    build_template_context,
    load_prompt_file,
    render_template,
)


class TestLoadPromptFile:
    def test_absolute_path(self, tmp_path):
        f = tmp_path / "prompt.md"
        f.write_text("Hello prompt")
        assert load_prompt_file(str(f), "/some/dir") == "Hello prompt"

    def test_relative_path(self, tmp_path):
        f = tmp_path / "prompts" / "stage.md"
        f.parent.mkdir()
        f.write_text("Stage prompt")
        assert load_prompt_file("prompts/stage.md", str(tmp_path)) == "Stage prompt"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_prompt_file("missing.md", str(tmp_path))


class TestRenderTemplate:
    def test_basic_substitution(self):
        result = render_template("Hello {{ name }}", {"name": "World"})
        assert result == "Hello World"

    def test_missing_variable_is_empty(self):
        result = render_template("Hello {{ missing }}", {})
        assert result == "Hello "

    def test_complex_template(self):
        result = render_template(
            "Issue: {{ issue_identifier }} - {{ issue_title }}",
            {"issue_identifier": "FIC-1", "issue_title": "Test"},
        )
        assert result == "Issue: FIC-1 - Test"


class TestSilentUndefined:
    def test_str_is_empty(self):
        assert str(_SilentUndefined()) == ""

    def test_bool_is_false(self):
        assert bool(_SilentUndefined()) is False

    def test_iter_is_empty(self):
        assert list(_SilentUndefined()) == []

    def test_getattr_returns_silent(self):
        u = _SilentUndefined()
        assert isinstance(u.foo, _SilentUndefined)

    def test_getitem_returns_silent(self):
        u = _SilentUndefined()
        assert isinstance(u["bar"], _SilentUndefined)


class TestBuildTemplateContext:
    def test_all_fields_present(self, sample_issue):
        ctx = build_template_context(sample_issue, "investigate", run=2, attempt=3)
        assert ctx["issue_id"] == "issue-1"
        assert ctx["issue_identifier"] == "FIC-1"
        assert ctx["issue_title"] == "Test issue"
        assert ctx["issue_description"] == "A test issue description"
        assert ctx["issue_url"] == "https://linear.app/test/issue/FIC-1"
        assert ctx["issue_priority"] == 2
        assert ctx["issue_state"] == "In Progress"
        assert ctx["issue_branch"] == "fic-1/test-issue"
        assert ctx["issue_labels"] == ["bug", "p0"]
        assert ctx["state_name"] == "investigate"
        assert ctx["run"] == 2
        assert ctx["attempt"] == 3

    def test_defaults_for_optional_fields(self, minimal_issue):
        ctx = build_template_context(minimal_issue, "s")
        assert ctx["issue_description"] == ""
        assert ctx["issue_url"] == ""
        assert ctx["issue_branch"] == ""
        assert ctx["last_run_at"] == ""

    def test_last_run_at(self, minimal_issue):
        ctx = build_template_context(
            minimal_issue, "s", last_run_at="2026-01-01T00:00:00Z"
        )
        assert ctx["last_run_at"] == "2026-01-01T00:00:00Z"


class TestBuildLifecycleSection:
    def test_contains_issue_metadata(self, sample_issue, sample_state_config):
        result = build_lifecycle_section(
            sample_issue, "investigate", sample_state_config, LinearStatesConfig()
        )
        assert "FIC-1" in result
        assert "Test issue" in result
        assert "investigate" in result

    def test_contains_transitions(self, sample_issue, sample_state_config):
        result = build_lifecycle_section(
            sample_issue, "investigate", sample_state_config, LinearStatesConfig()
        )
        assert "complete" in result
        assert "review-gate" in result

    def test_rework_section(self, sample_issue, sample_state_config):
        comments = [
            {"body": "Please fix the tests", "createdAt": "2026-01-01T00:00:00Z"}
        ]
        result = build_lifecycle_section(
            sample_issue,
            "investigate",
            sample_state_config,
            LinearStatesConfig(),
            is_rework=True,
            recent_comments=comments,
        )
        assert "Rework" in result or "rework" in result
        assert "Please fix the tests" in result

    def test_recent_activity_non_rework(self, sample_issue, sample_state_config):
        comments = [
            {"body": "Status update here", "createdAt": "2026-01-01T00:00:00Z"}
        ]
        result = build_lifecycle_section(
            sample_issue,
            "investigate",
            sample_state_config,
            LinearStatesConfig(),
            recent_comments=comments,
        )
        assert "Status update here" in result
        assert "Recent Activity" in result

    def test_no_transitions_still_valid(self, sample_issue):
        state_cfg = StateConfig(name="done", type="terminal")
        result = build_lifecycle_section(
            sample_issue, "done", state_cfg, LinearStatesConfig()
        )
        assert "Lifecycle Context" in result

    def test_auto_generated_markers(self, sample_issue, sample_state_config):
        result = build_lifecycle_section(
            sample_issue, "investigate", sample_state_config, LinearStatesConfig()
        )
        assert "AUTO-GENERATED BY CLAUDE SYMPHONY" in result
        assert "END CLAUDE SYMPHONY LIFECYCLE" in result

    def test_run_number_in_output(self, sample_issue, sample_state_config):
        result = build_lifecycle_section(
            sample_issue, "investigate", sample_state_config, LinearStatesConfig(),
            run=5,
        )
        assert "5" in result


class TestAssemblePrompt:
    def test_three_layers(self, tmp_path, sample_issue):
        # Create prompt files
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        (prompts / "global.md").write_text("Global: {{ issue_identifier }}")
        (prompts / "stage.md").write_text("Stage: {{ state_name }}")

        cfg = ServiceConfig(
            prompts=PromptsConfig(global_prompt="prompts/global.md"),
            linear_states=LinearStatesConfig(),
            states={
                "investigate": StateConfig(
                    name="investigate", type="agent",
                    prompt="prompts/stage.md",
                ),
            },
        )
        state_cfg = cfg.states["investigate"]

        result = assemble_prompt(
            cfg, str(tmp_path), sample_issue,
            "investigate", state_cfg, run=1,
        )
        assert "Global: FIC-1" in result
        assert "Stage: investigate" in result
        assert "Lifecycle Context" in result

    def test_missing_global_prompt_continues(self, tmp_path, sample_issue):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        (prompts / "stage.md").write_text("Stage only")

        cfg = ServiceConfig(
            prompts=PromptsConfig(global_prompt="missing_global.md"),
            linear_states=LinearStatesConfig(),
            states={
                "s": StateConfig(name="s", type="agent", prompt="prompts/stage.md"),
            },
        )
        # Should not raise — missing global is a warning
        result = assemble_prompt(
            cfg, str(tmp_path), sample_issue, "s", cfg.states["s"]
        )
        assert "Stage only" in result
        assert "Lifecycle Context" in result

    def test_no_global_prompt_configured(self, tmp_path, sample_issue):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        (prompts / "stage.md").write_text("Stage text")

        cfg = ServiceConfig(
            prompts=PromptsConfig(global_prompt=None),
            linear_states=LinearStatesConfig(),
            states={
                "s": StateConfig(name="s", type="agent", prompt="prompts/stage.md"),
            },
        )
        result = assemble_prompt(
            cfg, str(tmp_path), sample_issue, "s", cfg.states["s"]
        )
        assert "Stage text" in result
        # Should not contain "Global" since none configured
