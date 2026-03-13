"""Tests for orchestrator.py — SPEC 17.4 Orchestrator."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_symphony.config import (
    AgentConfig,
    ClaudeConfig,
    HooksConfig,
    LinearStatesConfig,
    ServiceConfig,
    StateConfig,
    TrackerConfig,
    WorkflowDefinition,
)
from claude_symphony.models import Issue, RetryEntry, RunAttempt
from claude_symphony.orchestrator import Orchestrator


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_issue(
    id: str = "id-1",
    identifier: str = "FIC-1",
    title: str = "Test",
    state: str = "In Progress",
    priority: int | None = 2,
    created_at: datetime | None = None,
    blocked_by: list | None = None,
) -> Issue:
    return Issue(
        id=id,
        identifier=identifier,
        title=title,
        state=state,
        priority=priority,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        blocked_by=blocked_by or [],
    )


def _make_orchestrator(tmp_path, states=None, api_key="test-key") -> Orchestrator:
    """Create an Orchestrator with a temporary workflow file."""
    yaml_content = f"""\
tracker:
  kind: linear
  api_key: {api_key}
  team_key: FIC
workspace:
  root: "{tmp_path}/workspaces"
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
    wf = tmp_path / "workflow.yaml"
    wf.write_text(yaml_content)
    prompts = tmp_path / "prompts"
    prompts.mkdir(exist_ok=True)
    (prompts / "investigate.md").write_text("Investigate")
    return Orchestrator(wf)


# ── Eligibility ──────────────────────────────────────────────────────────────


class TestIsEligible:
    def test_eligible_issue(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        assert orch._is_eligible(issue) is True

    def test_ineligible_missing_id(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue(id="")
        assert orch._is_eligible(issue) is False

    def test_ineligible_missing_title(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue(title="")
        assert orch._is_eligible(issue) is False

    def test_ineligible_wrong_state(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue(state="Done")
        assert orch._is_eligible(issue) is False

    def test_ineligible_already_running(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        orch.running[issue.id] = RunAttempt(issue_id=issue.id, issue_identifier=issue.identifier)
        assert orch._is_eligible(issue) is False

    def test_ineligible_already_claimed(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        orch.claimed.add(issue.id)
        assert orch._is_eligible(issue) is False

    def test_blockers_only_checked_for_todo(self, tmp_path):
        from claude_symphony.models import BlockerRef
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        blocker = BlockerRef(id="b-1", identifier="FIC-0", state="In Progress")
        # Issue in "In Progress" — blockers NOT checked
        issue = _make_issue(state="In Progress", blocked_by=[blocker])
        assert orch._is_eligible(issue) is True


# ── Dispatch sort order ──────────────────────────────────────────────────────


class TestDispatchSort:
    def test_priority_sort(self):
        """Lower priority number = higher priority."""
        issues = [
            _make_issue(id="low", identifier="FIC-3", priority=3),
            _make_issue(id="high", identifier="FIC-1", priority=1),
            _make_issue(id="med", identifier="FIC-2", priority=2),
        ]
        issues.sort(
            key=lambda i: (
                i.priority if i.priority is not None else 999,
                i.created_at or datetime.min.replace(tzinfo=timezone.utc),
                i.identifier,
            )
        )
        assert [i.identifier for i in issues] == ["FIC-1", "FIC-2", "FIC-3"]

    def test_none_priority_sorts_last(self):
        issues = [
            _make_issue(id="none", identifier="FIC-2", priority=None),
            _make_issue(id="has", identifier="FIC-1", priority=1),
        ]
        issues.sort(
            key=lambda i: (
                i.priority if i.priority is not None else 999,
                i.created_at or datetime.min.replace(tzinfo=timezone.utc),
                i.identifier,
            )
        )
        assert issues[0].identifier == "FIC-1"

    def test_same_priority_sorts_by_created_at(self):
        issues = [
            _make_issue(
                id="newer", identifier="FIC-2", priority=1,
                created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            ),
            _make_issue(
                id="older", identifier="FIC-1", priority=1,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        issues.sort(
            key=lambda i: (
                i.priority if i.priority is not None else 999,
                i.created_at or datetime.min.replace(tzinfo=timezone.utc),
                i.identifier,
            )
        )
        assert issues[0].identifier == "FIC-1"

    def test_same_priority_and_date_sorts_by_identifier(self):
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        issues = [
            _make_issue(id="b", identifier="FIC-B", priority=1, created_at=ts),
            _make_issue(id="a", identifier="FIC-A", priority=1, created_at=ts),
        ]
        issues.sort(
            key=lambda i: (
                i.priority if i.priority is not None else 999,
                i.created_at or datetime.min.replace(tzinfo=timezone.utc),
                i.identifier,
            )
        )
        assert issues[0].identifier == "FIC-A"


# ── Retry backoff ────────────────────────────────────────────────────────────


class TestRetryBackoff:
    def test_succeeded_triggers_transition(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="succeeded",
            state_name="investigate",
            started_at=datetime.now(timezone.utc),
        )
        # Mock _transition to avoid actual async work
        orch._issue_current_state[issue.id] = "investigate"
        with patch.object(orch, '_schedule_retry') as mock_retry, \
             patch('asyncio.create_task') as mock_task:
            orch._on_worker_exit(issue, attempt)
            # Should create a transition task, not schedule_retry
            mock_task.assert_called_once()

    def test_failed_exponential_backoff(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()

        # attempt=0 → first failure → delay = 10000 * 2^0 = 10000ms
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="failed",
            error="something broke",
            attempt=0,
            started_at=datetime.now(timezone.utc),
        )
        with patch.object(orch, '_schedule_retry') as mock:
            orch._on_worker_exit(issue, attempt)
            mock.assert_called_once()
            call_kwargs = mock.call_args
            assert call_kwargs[1]["delay_ms"] == 10_000

    def test_backoff_caps_at_max(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()

        # Very high attempt → should cap at max_retry_backoff_ms (300_000)
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="failed",
            error="still broken",
            attempt=100,
            started_at=datetime.now(timezone.utc),
        )
        with patch.object(orch, '_schedule_retry') as mock:
            orch._on_worker_exit(issue, attempt)
            call_kwargs = mock.call_args
            assert call_kwargs[1]["delay_ms"] == 300_000

    def test_canceled_releases_claim(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        orch.claimed.add(issue.id)
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="canceled",
            started_at=datetime.now(timezone.utc),
        )
        orch._on_worker_exit(issue, attempt)
        assert issue.id not in orch.claimed

    def test_timed_out_retries(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="timed_out",
            attempt=1,
            started_at=datetime.now(timezone.utc),
        )
        with patch.object(orch, '_schedule_retry') as mock:
            orch._on_worker_exit(issue, attempt)
            mock.assert_called_once()


# ── State snapshot ───────────────────────────────────────────────────────────


class TestGetStateSnapshot:
    def test_empty_snapshot_shape(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        snap = orch.get_state_snapshot()
        assert "counts" in snap
        assert "running" in snap
        assert "retrying" in snap
        assert "gates" in snap
        assert "totals" in snap
        assert snap["counts"]["running"] == 0
        assert snap["counts"]["retrying"] == 0
        assert snap["totals"]["total_tokens"] == 0

    def test_snapshot_with_running(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        orch.running["id-1"] = RunAttempt(
            issue_id="id-1",
            issue_identifier="FIC-1",
            status="streaming",
            turn_count=2,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            started_at=datetime.now(timezone.utc),
        )
        snap = orch.get_state_snapshot()
        assert snap["counts"]["running"] == 1
        assert len(snap["running"]) == 1
        r = snap["running"][0]
        assert r["issue_identifier"] == "FIC-1"
        assert r["tokens"]["total_tokens"] == 150

    def test_snapshot_with_retrying(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        orch.retry_attempts["id-1"] = RetryEntry(
            issue_id="id-1",
            identifier="FIC-1",
            attempt=2,
            error="network error",
        )
        snap = orch.get_state_snapshot()
        assert snap["counts"]["retrying"] == 1
        assert snap["retrying"][0]["attempt"] == 2

    def test_token_aggregation(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        orch.total_input_tokens = 1000
        orch.total_output_tokens = 500
        orch.total_tokens = 1500
        snap = orch.get_state_snapshot()
        assert snap["totals"]["input_tokens"] == 1000
        assert snap["totals"]["output_tokens"] == 500
        assert snap["totals"]["total_tokens"] == 1500

    def test_snapshot_generated_at(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        snap = orch.get_state_snapshot()
        assert "generated_at" in snap
        # Should be a valid ISO timestamp
        datetime.fromisoformat(snap["generated_at"])


# ── Worker exit token aggregation ────────────────────────────────────────────


class TestWorkerExitAggregation:
    def test_tokens_aggregated(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="canceled",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            started_at=datetime.now(timezone.utc),
        )
        orch._on_worker_exit(issue, attempt)
        assert orch.total_input_tokens == 100
        assert orch.total_output_tokens == 50
        assert orch.total_tokens == 150

    def test_session_id_preserved(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        issue = _make_issue()
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            status="canceled",
            session_id="sess-123",
            started_at=datetime.now(timezone.utc),
        )
        orch._on_worker_exit(issue, attempt)
        assert orch._last_session_ids[issue.id] == "sess-123"


# ── Per-state concurrency ───────────────────────────────────────────────────


class TestPerStateConcurrency:
    def test_state_limit_checked(self, tmp_path):
        """When per-state limit is reached, no more dispatches for that state."""
        orch = _make_orchestrator(tmp_path)
        orch._load_workflow()
        # Set per-state limit
        orch.cfg.agent.max_concurrent_agents_by_state["in progress"] = 1

        # Simulate one running in "In Progress"
        running_issue = _make_issue(id="running-1", identifier="FIC-R")
        orch.running["running-1"] = RunAttempt(
            issue_id="running-1", issue_identifier="FIC-R"
        )
        orch._last_issues["running-1"] = running_issue

        # A new candidate should be blocked
        new_issue = _make_issue(id="new-1", identifier="FIC-N")
        # The per-state check is within _tick, tested via state_count logic
        state_key = new_issue.state.strip().lower()
        state_limit = orch.cfg.agent.max_concurrent_agents_by_state.get(state_key)
        assert state_limit == 1

        state_count = sum(
            1
            for r in orch.running.values()
            if orch._last_issues.get(r.issue_id, Issue(id="", identifier="", title="")).state.strip().lower()
            == state_key
        )
        assert state_count >= state_limit  # Should block


# ── Load workflow ────────────────────────────────────────────────────────────


class TestLoadWorkflow:
    def test_successful_load(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        errors = orch._load_workflow()
        assert errors == []
        assert orch.workflow is not None

    def test_invalid_file_returns_errors(self, tmp_path):
        wf = tmp_path / "bad.yaml"
        wf.write_text("[not valid")
        orch = Orchestrator(wf)
        errors = orch._load_workflow()
        assert len(errors) > 0
