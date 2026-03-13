"""Tests for events.py — SPEC 17.6 Observability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from claude_symphony.events import (
    AgentEvent,
    EventBuffer,
    _extract_text,
    _tool_input_preview,
    classify_event,
)


class TestExtractText:
    def test_string_content(self):
        assert _extract_text({"content": "hello"}) == "hello"

    def test_message_with_string_content(self):
        event = {"message": {"content": "msg text"}}
        assert _extract_text(event) == "msg text"

    def test_message_with_list_content(self):
        event = {
            "message": {
                "content": [
                    {"type": "text", "text": "first block"},
                    {"type": "text", "text": "second"},
                ]
            }
        }
        assert _extract_text(event) == "first block"

    def test_tool_result_string(self):
        event = {"type": "tool_result", "content": "result text"}
        assert _extract_text(event) == "result text"

    def test_tool_result_list_via_message(self):
        # tool_result list path requires "message" to not short-circuit
        event = {
            "type": "tool_result",
            "content": [{"type": "text", "text": "list result"}],
            "message": {"content": [{"type": "text", "text": "list result"}]},
        }
        assert _extract_text(event) == "list result"

    def test_result_field_fallback(self):
        # "result" field fallback requires message.content to not be a string
        event = {"result": "final result", "message": {"content": []}}
        assert _extract_text(event) == "final result"

    def test_empty_event(self):
        assert _extract_text({}) == ""

    def test_non_text_blocks_skipped(self):
        event = {
            "message": {
                "content": [{"type": "image", "url": "x"}, {"type": "text", "text": "found"}]
            }
        }
        assert _extract_text(event) == "found"


class TestToolInputPreview:
    def test_known_tool_field(self):
        assert _tool_input_preview("Bash", {"command": "ls -la"}) == "ls -la"

    def test_known_tool_read(self):
        assert _tool_input_preview("Read", {"file_path": "/foo/bar.py"}) == "/foo/bar.py"

    def test_known_tool_grep(self):
        assert _tool_input_preview("Grep", {"pattern": "TODO"}) == "TODO"

    def test_unknown_tool_uses_first_string_value(self):
        result = _tool_input_preview("CustomTool", {"arg": "value"})
        assert result == "value"

    def test_truncates_long_values(self):
        long_val = "x" * 200
        result = _tool_input_preview("Bash", {"command": long_val})
        assert len(result) == 120

    def test_empty_input(self):
        assert _tool_input_preview("Bash", {}) == ""


class TestClassifyEvent:
    def test_assistant_event(self):
        event = {"type": "assistant", "message": {"content": "thinking..."}}
        result = classify_event(event)
        assert result is not None
        assert result.event_type == "thinking"
        assert result.summary == "thinking..."

    def test_tool_use_event(self):
        event = {
            "type": "tool_use",
            "name": "Bash",
            "input": {"command": "git status"},
        }
        result = classify_event(event)
        assert result is not None
        assert result.event_type == "tool_use"
        assert "Bash" in result.summary
        assert "git status" in result.summary
        assert result.tool_name == "Bash"

    def test_tool_result_event(self):
        event = {"type": "tool_result", "content": "output here", "is_error": False}
        result = classify_event(event)
        assert result is not None
        assert result.event_type == "tool_result"

    def test_tool_result_error(self):
        event = {"type": "tool_result", "content": "error msg", "is_error": True}
        result = classify_event(event)
        assert result.event_type == "error"

    def test_result_event(self):
        event = {"type": "result", "result": "final answer"}
        result = classify_event(event)
        assert result is not None
        assert result.event_type == "result"
        assert result.summary == "final answer"

    def test_unknown_event_returns_none(self):
        assert classify_event({"type": "system"}) is None

    def test_assistant_empty_content_returns_none(self):
        event = {"type": "assistant", "message": {"content": ""}}
        assert classify_event(event) is None

    def test_long_summary_truncated(self):
        event = {"type": "assistant", "message": {"content": "x" * 500}}
        result = classify_event(event)
        assert len(result.summary) == 200


class TestEventBuffer:
    def test_push_and_get(self):
        buf = EventBuffer(max_events=10)
        event = AgentEvent(
            timestamp=datetime.now(timezone.utc),
            event_type="thinking",
            summary="test",
        )
        buf.push("issue-1", event)
        result = buf.get("issue-1")
        assert len(result) == 1
        assert result[0].summary == "test"

    def test_get_empty(self):
        buf = EventBuffer()
        assert buf.get("nonexistent") == []

    def test_ring_buffer_capacity(self):
        buf = EventBuffer(max_events=3)
        for i in range(5):
            buf.push(
                "issue-1",
                AgentEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="thinking",
                    summary=f"event-{i}",
                ),
            )
        result = buf.get("issue-1")
        assert len(result) == 3
        assert result[0].summary == "event-2"  # oldest kept

    def test_get_with_limit(self):
        buf = EventBuffer(max_events=10)
        for i in range(5):
            buf.push(
                "issue-1",
                AgentEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="thinking",
                    summary=f"event-{i}",
                ),
            )
        result = buf.get("issue-1", limit=2)
        assert len(result) == 2
        assert result[0].summary == "event-3"

    def test_get_since(self):
        buf = EventBuffer()
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=1)
        buf.push("issue-1", AgentEvent(timestamp=old, event_type="t", summary="old"))
        buf.push("issue-1", AgentEvent(timestamp=now, event_type="t", summary="new"))
        result = buf.get_since("issue-1", now - timedelta(minutes=1))
        assert len(result) == 1
        assert result[0].summary == "new"

    def test_count(self):
        buf = EventBuffer()
        assert buf.count("issue-1") == 0
        buf.push(
            "issue-1",
            AgentEvent(timestamp=datetime.now(timezone.utc), event_type="t", summary="s"),
        )
        assert buf.count("issue-1") == 1

    def test_clear(self):
        buf = EventBuffer()
        buf.push(
            "issue-1",
            AgentEvent(timestamp=datetime.now(timezone.utc), event_type="t", summary="s"),
        )
        buf.clear("issue-1")
        assert buf.count("issue-1") == 0
        assert buf.get("issue-1") == []

    def test_separate_issue_buffers(self):
        buf = EventBuffer()
        buf.push(
            "issue-1",
            AgentEvent(timestamp=datetime.now(timezone.utc), event_type="t", summary="a"),
        )
        buf.push(
            "issue-2",
            AgentEvent(timestamp=datetime.now(timezone.utc), event_type="t", summary="b"),
        )
        assert buf.count("issue-1") == 1
        assert buf.count("issue-2") == 1
        assert buf.get("issue-1")[0].summary == "a"
