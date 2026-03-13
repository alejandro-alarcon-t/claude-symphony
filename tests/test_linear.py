"""Tests for linear.py — SPEC 17.3 Linear Client."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_symphony.linear import LinearClient, _normalize_issue, _parse_datetime


class TestParseDatetime:
    def test_iso_format(self):
        result = _parse_datetime("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_none_input(self):
        assert _parse_datetime(None) is None

    def test_empty_string(self):
        assert _parse_datetime("") is None

    def test_invalid_format(self):
        assert _parse_datetime("not-a-date") is None


class TestNormalizeIssue:
    def test_basic_fields(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "description": "desc",
            "priority": 2,
            "state": {"name": "In Progress"},
            "url": "https://example.com",
            "branchName": "fic-1/test",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-02T00:00:00Z",
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.id == "id-1"
        assert issue.identifier == "FIC-1"
        assert issue.title == "Test"
        assert issue.priority == 2
        assert issue.state == "In Progress"
        assert issue.branch_name == "fic-1/test"

    def test_labels_lowercased(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "labels": {"nodes": [{"name": "Bug"}, {"name": "P0"}]},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.labels == ["bug", "p0"]

    def test_blocker_extraction(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "labels": {"nodes": []},
            "inverseRelations": {
                "nodes": [
                    {
                        "type": "blocks",
                        "relatedIssue": {
                            "id": "blocker-1",
                            "identifier": "FIC-0",
                            "state": {"name": "Todo"},
                        },
                    },
                    {
                        "type": "relates",
                        "relatedIssue": {
                            "id": "rel-1",
                            "identifier": "FIC-2",
                            "state": {"name": "Done"},
                        },
                    },
                ]
            },
        }
        issue = _normalize_issue(node)
        assert len(issue.blocked_by) == 1
        assert issue.blocked_by[0].identifier == "FIC-0"

    def test_priority_coercion(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "priority": "3",
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.priority == 3

    def test_priority_none(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "priority": None,
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.priority is None

    def test_priority_invalid(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "priority": "high",
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.priority is None

    def test_parent_and_siblings(self):
        node = {
            "id": "child-1",
            "identifier": "FIC-3",
            "title": "Child",
            "state": {"name": "In Progress"},
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
            "parent": {
                "id": "parent-1",
                "identifier": "FIC-EPIC",
                "title": "Epic",
                "state": {"name": "In Progress"},
                "labels": {"nodes": [{"name": "Epic"}]},
                "children": {
                    "nodes": [
                        {
                            "id": "child-1",
                            "identifier": "FIC-3",
                            "title": "Child",
                            "state": {"name": "In Progress"},
                            "labels": {"nodes": []},
                        },
                        {
                            "id": "sibling-1",
                            "identifier": "FIC-4",
                            "title": "Sibling",
                            "state": {"name": "Done"},
                            "labels": {"nodes": [{"name": "Feature"}]},
                        },
                    ]
                },
            },
        }
        issue = _normalize_issue(node)
        assert issue.parent is not None
        assert issue.parent.identifier == "FIC-EPIC"
        assert issue.parent.labels == ["epic"]
        assert len(issue.siblings) == 1
        assert issue.siblings[0].identifier == "FIC-4"
        assert issue.siblings[0].labels == ["feature"]

    def test_no_parent(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.parent is None
        assert issue.siblings == []

    def test_missing_state_fallback(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": None,
            "labels": {"nodes": []},
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.state == ""

    def test_null_labels_handled(self):
        node = {
            "id": "id-1",
            "identifier": "FIC-1",
            "title": "Test",
            "state": {"name": "In Progress"},
            "labels": None,
            "inverseRelations": {"nodes": []},
        }
        issue = _normalize_issue(node)
        assert issue.labels == []


class TestLinearClientInit:
    def test_client_setup(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
            timeout_ms=5000,
            team_key="FIC",
        )
        assert client.endpoint == "https://api.linear.app/graphql"
        assert client.api_key == "test-key"
        assert client.timeout == 5.0
        assert client.team_key == "FIC"


class TestLinearClientMethods:
    @pytest.mark.asyncio
    async def test_fetch_issue_states_empty(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
        )
        result = await client.fetch_issue_states_by_ids([])
        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_candidate_issues_team_key(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
            team_key="FIC",
        )
        # Mock the _graphql method
        client._graphql = AsyncMock(return_value={
            "issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "id": "id-1",
                        "identifier": "FIC-1",
                        "title": "Test",
                        "state": {"name": "In Progress"},
                        "labels": {"nodes": []},
                        "inverseRelations": {"nodes": []},
                    }
                ],
            }
        })
        issues = await client.fetch_candidate_issues("slug", ["In Progress"])
        assert len(issues) == 1
        assert issues[0].identifier == "FIC-1"
        # Verify team key query was used
        call_args = client._graphql.call_args
        assert "teamKey" in call_args[0][1]
        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_candidate_issues_project_slug(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
        )
        client._graphql = AsyncMock(return_value={
            "issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [],
            }
        })
        await client.fetch_candidate_issues("my-slug", ["In Progress"])
        call_args = client._graphql.call_args
        assert "projectSlug" in call_args[0][1]
        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_issue_states_by_ids(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
        )
        client._graphql = AsyncMock(return_value={
            "issues": {
                "nodes": [
                    {"id": "id-1", "identifier": "FIC-1", "state": {"name": "Done"}},
                ]
            }
        })
        result = await client.fetch_issue_states_by_ids(["id-1"])
        assert result == {"id-1": "Done"}
        await client.close()

    @pytest.mark.asyncio
    async def test_post_comment(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
        )
        client._graphql = AsyncMock(return_value={
            "commentCreate": {"success": True, "comment": {"id": "c-1"}}
        })
        result = await client.post_comment("issue-1", "Hello")
        assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_post_comment_failure(self):
        client = LinearClient(
            endpoint="https://api.linear.app/graphql",
            api_key="test-key",
        )
        client._graphql = AsyncMock(side_effect=RuntimeError("API error"))
        result = await client.post_comment("issue-1", "Hello")
        assert result is False
        await client.close()
