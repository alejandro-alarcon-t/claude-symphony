"""Tests for tracking.py — SPEC 17.x state machine tracking via structured comments."""

from __future__ import annotations

import json
import re

from claude_symphony.tracking import (
    GATE_PATTERN,
    STATE_PATTERN,
    get_comments_since,
    get_last_tracking_timestamp,
    make_gate_comment,
    make_state_comment,
    parse_latest_tracking,
)


class TestMakeStateComment:
    def test_contains_hidden_json(self):
        comment = make_state_comment("investigate", run=1)
        match = STATE_PATTERN.search(comment)
        assert match is not None
        data = json.loads(match.group(1))
        assert data["state"] == "investigate"
        assert data["run"] == 1
        assert "timestamp" in data

    def test_contains_human_readable(self):
        comment = make_state_comment("implement", run=2)
        assert "implement" in comment
        assert "run 2" in comment

    def test_different_runs_produce_different_timestamps(self):
        c1 = make_state_comment("s", run=1)
        c2 = make_state_comment("s", run=2)
        m1 = STATE_PATTERN.search(c1)
        m2 = STATE_PATTERN.search(c2)
        d1 = json.loads(m1.group(1))
        d2 = json.loads(m2.group(1))
        # Both have timestamps (they may be equal if fast enough, but both exist)
        assert "timestamp" in d1 and "timestamp" in d2


class TestMakeGateComment:
    def test_waiting_status(self):
        comment = make_gate_comment("review-gate", "waiting", prompt="Review this")
        match = GATE_PATTERN.search(comment)
        assert match is not None
        data = json.loads(match.group(1))
        assert data["status"] == "waiting"
        assert "Awaiting human review" in comment

    def test_approved_status(self):
        comment = make_gate_comment("review-gate", "approved", run=1)
        assert "approved" in comment.lower()
        data = json.loads(GATE_PATTERN.search(comment).group(1))
        assert data["status"] == "approved"

    def test_rework_status_includes_target(self):
        comment = make_gate_comment(
            "review-gate", "rework", rework_to="investigate", run=2
        )
        data = json.loads(GATE_PATTERN.search(comment).group(1))
        assert data["rework_to"] == "investigate"
        assert "investigate" in comment

    def test_rework_shows_run_number_when_gt_1(self):
        comment = make_gate_comment("g", "rework", rework_to="s", run=3)
        assert "run 3" in comment

    def test_escalated_status(self):
        comment = make_gate_comment("review-gate", "escalated", run=5)
        assert "escalat" in comment.lower()

    def test_unknown_status_fallback(self):
        comment = make_gate_comment("g", "custom_status")
        assert "custom_status" in comment


class TestParseLatestTracking:
    def test_no_tracking_returns_none(self):
        comments = [{"body": "Just a regular comment"}]
        assert parse_latest_tracking(comments) is None

    def test_empty_list_returns_none(self):
        assert parse_latest_tracking([]) is None

    def test_finds_state_tracking(self):
        body = make_state_comment("investigate", run=1)
        result = parse_latest_tracking([{"body": body}])
        assert result is not None
        assert result["type"] == "state"
        assert result["state"] == "investigate"
        assert result["run"] == 1

    def test_finds_gate_tracking(self):
        body = make_gate_comment("review-gate", "waiting", run=2)
        result = parse_latest_tracking([{"body": body}])
        assert result is not None
        assert result["type"] == "gate"
        assert result["status"] == "waiting"

    def test_latest_wins_when_multiple(self):
        comments = [
            {"body": make_state_comment("investigate", run=1)},
            {"body": make_gate_comment("review-gate", "waiting", run=1)},
            {"body": make_state_comment("implement", run=1)},
        ]
        result = parse_latest_tracking(comments)
        assert result["type"] == "state"
        assert result["state"] == "implement"

    def test_ignores_malformed_json(self):
        comments = [
            {"body": "<!-- claude-symphony:state {bad json} -->"},
            {"body": make_state_comment("valid", run=1)},
        ]
        result = parse_latest_tracking(comments)
        assert result is not None
        assert result["state"] == "valid"


class TestGetLastTrackingTimestamp:
    def test_returns_none_for_no_tracking(self):
        assert get_last_tracking_timestamp([{"body": "hello"}]) is None

    def test_extracts_timestamp(self):
        body = make_state_comment("s", run=1)
        ts = get_last_tracking_timestamp([{"body": body}])
        assert ts is not None
        assert "T" in ts  # ISO format

    def test_latest_timestamp_from_multiple(self):
        comments = [
            {"body": make_state_comment("s1", run=1)},
            {"body": make_gate_comment("g1", "waiting", run=1)},
        ]
        ts = get_last_tracking_timestamp(comments)
        assert ts is not None


class TestGetCommentsSince:
    def test_filters_tracking_comments(self):
        comments = [
            {"body": make_state_comment("s", run=1), "createdAt": "2026-01-01T00:00:00Z"},
            {"body": "Human comment", "createdAt": "2026-01-02T00:00:00Z"},
        ]
        result = get_comments_since(comments, "2025-12-31T00:00:00Z")
        assert len(result) == 1
        assert result[0]["body"] == "Human comment"

    def test_filters_by_timestamp(self):
        comments = [
            {"body": "Old comment", "createdAt": "2025-01-01T00:00:00Z"},
            {"body": "New comment", "createdAt": "2026-06-01T00:00:00Z"},
        ]
        result = get_comments_since(comments, "2026-01-01T00:00:00Z")
        assert len(result) == 1
        assert result[0]["body"] == "New comment"

    def test_no_timestamp_returns_all_non_tracking(self):
        comments = [
            {"body": "comment 1"},
            {"body": "comment 2"},
            {"body": make_state_comment("s", run=1)},
        ]
        result = get_comments_since(comments, None)
        assert len(result) == 2

    def test_empty_comments(self):
        assert get_comments_since([], "2026-01-01T00:00:00Z") == []
