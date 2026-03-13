"""Shared fixtures for claude_symphony tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_symphony.config import (
    AgentConfig,
    ClaudeConfig,
    HooksConfig,
    LinearStatesConfig,
    PollingConfig,
    PromptsConfig,
    ServerConfig,
    ServiceConfig,
    StateConfig,
    TrackerConfig,
    WorkspaceConfig,
)
from claude_symphony.models import BlockerRef, Issue, IssueRef, RetryEntry, RunAttempt


@pytest.fixture
def sample_issue() -> Issue:
    return Issue(
        id="issue-1",
        identifier="FIC-1",
        title="Test issue",
        description="A test issue description",
        priority=2,
        state="In Progress",
        branch_name="fic-1/test-issue",
        url="https://linear.app/test/issue/FIC-1",
        labels=["bug", "p0"],
        blocked_by=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_issue_with_parent() -> Issue:
    parent = IssueRef(
        id="parent-1",
        identifier="FIC-EPIC",
        title="Epic",
        state="In Progress",
        labels=["epic"],
    )
    sibling = IssueRef(
        id="sibling-1",
        identifier="FIC-2",
        title="Sibling",
        state="Done",
        labels=["feature"],
    )
    return Issue(
        id="issue-2",
        identifier="FIC-2",
        title="Child issue",
        priority=1,
        state="In Progress",
        parent=parent,
        siblings=[sibling],
    )


@pytest.fixture
def minimal_issue() -> Issue:
    return Issue(id="id-min", identifier="FIC-99", title="Minimal")


@pytest.fixture
def sample_run_attempt() -> RunAttempt:
    return RunAttempt(
        issue_id="issue-1",
        issue_identifier="FIC-1",
        attempt=1,
        status="pending",
    )


@pytest.fixture
def sample_hooks() -> HooksConfig:
    return HooksConfig(
        after_create="echo created",
        before_remove="echo removing",
        timeout_ms=5000,
    )


@pytest.fixture
def sample_claude_config() -> ClaudeConfig:
    return ClaudeConfig(
        command="claude",
        permission_mode="auto",
        model="sonnet",
        max_turns=5,
        turn_timeout_ms=60_000,
        stall_timeout_ms=30_000,
    )


@pytest.fixture
def sample_state_config() -> StateConfig:
    return StateConfig(
        name="investigate",
        type="agent",
        prompt="prompts/investigate.md",
        linear_state="active",
        transitions={"complete": "review-gate"},
    )


@pytest.fixture
def sample_gate_config() -> StateConfig:
    return StateConfig(
        name="review-gate",
        type="gate",
        linear_state="review",
        rework_to="investigate",
        transitions={"approve": "implement"},
    )


@pytest.fixture
def sample_service_config() -> ServiceConfig:
    return ServiceConfig(
        tracker=TrackerConfig(
            api_key="test-key",
            team_key="FIC",
        ),
        claude=ClaudeConfig(command="claude", permission_mode="auto"),
        hooks=HooksConfig(),
        linear_states=LinearStatesConfig(),
        states={
            "investigate": StateConfig(
                name="investigate",
                type="agent",
                prompt="prompts/investigate.md",
                linear_state="active",
                transitions={"complete": "review-gate"},
            ),
            "review-gate": StateConfig(
                name="review-gate",
                type="gate",
                linear_state="review",
                rework_to="investigate",
                transitions={"approve": "implement"},
            ),
            "implement": StateConfig(
                name="implement",
                type="agent",
                prompt="prompts/implement.md",
                linear_state="active",
                transitions={"complete": "done"},
            ),
            "done": StateConfig(
                name="done",
                type="terminal",
                linear_state="terminal",
            ),
        },
    )


MINIMAL_WORKFLOW_YAML = """\
tracker:
  kind: linear
  api_key: test-key
  team_key: FIC
claude:
  command: claude
  permission_mode: auto
  max_turns: 10
states:
  investigate:
    type: agent
    prompt: prompts/investigate.md
    linear_state: active
    transitions:
      complete: done
  done:
    type: terminal
    linear_state: terminal
"""


@pytest.fixture
def workflow_yaml(tmp_path: Path) -> Path:
    """Create a minimal workflow.yaml in tmp_path."""
    wf = tmp_path / "workflow.yaml"
    wf.write_text(MINIMAL_WORKFLOW_YAML)
    # Create the prompt file referenced by the config
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "investigate.md").write_text("Investigate {{ issue_title }}")
    return wf
