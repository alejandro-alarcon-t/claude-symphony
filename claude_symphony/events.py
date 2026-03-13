"""Event buffer system for real-time agent activity tracking."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class AgentEvent:
    """A single event from the agent's stream-json output."""

    timestamp: datetime
    event_type: str  # "thinking", "tool_use", "tool_result", "error", "result"
    summary: str  # Human-readable one-liner
    detail: str | None = None  # Full content (for expand-on-click)
    tool_name: str | None = None
    tool_input: str | None = None


# Map tool names to their most informative input field for one-line summaries
_TOOL_PREVIEW_FIELDS = {
    "Bash": "command",
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "Grep": "pattern",
    "Glob": "pattern",
    "Agent": "prompt",
    "WebSearch": "query",
    "WebFetch": "url",
}


def _extract_text(event: dict) -> str:
    """Extract text content from an assistant or tool_result event."""
    if isinstance(event.get("content"), str):
        return event["content"]
    msg = event.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    if event.get("type") == "tool_result":
        result_content = event.get("content", "")
        if isinstance(result_content, str):
            return result_content
        if isinstance(result_content, list):
            for block in result_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
    if "result" in event and isinstance(event["result"], str):
        return event["result"]
    return ""


def _tool_input_preview(tool_name: str, inp: dict) -> str:
    """Extract the most informative field from a tool's input for the summary."""
    key = _TOOL_PREVIEW_FIELDS.get(tool_name)
    if key and key in inp:
        val = str(inp[key])
        return val[:120]
    for v in inp.values():
        if isinstance(v, str):
            return v[:80]
    return ""


def classify_event(event: dict) -> AgentEvent | None:
    """Classify a raw NDJSON event into an AgentEvent for the dashboard."""
    etype = event.get("type", "")
    now = datetime.now(timezone.utc)

    if etype == "assistant":
        content = _extract_text(event)
        if content:
            return AgentEvent(
                timestamp=now,
                event_type="thinking",
                summary=content[:200],
                detail=content if len(content) > 200 else None,
            )

    elif etype == "tool_use":
        tool = event.get("name", event.get("tool", ""))
        inp = event.get("input", {})
        preview = _tool_input_preview(tool, inp)
        return AgentEvent(
            timestamp=now,
            event_type="tool_use",
            summary=f"{tool}: {preview}" if preview else tool,
            tool_name=tool,
            tool_input=json.dumps(inp)[:500] if inp else None,
        )

    elif etype == "tool_result":
        content = _extract_text(event)
        is_error = event.get("is_error", False)
        return AgentEvent(
            timestamp=now,
            event_type="error" if is_error else "tool_result",
            summary=content[:200] if content else "Done",
            detail=content if content and len(content) > 200 else None,
        )

    elif etype == "result":
        result_text = event.get("result", "")
        if isinstance(result_text, str) and result_text:
            return AgentEvent(
                timestamp=now,
                event_type="result",
                summary=result_text[:200],
            )

    return None


class EventBuffer:
    """Per-issue ring buffer for recent agent events."""

    def __init__(self, max_events: int = 200):
        self._buffers: dict[str, deque[AgentEvent]] = {}
        self._max = max_events

    def push(self, issue_id: str, event: AgentEvent):
        if issue_id not in self._buffers:
            self._buffers[issue_id] = deque(maxlen=self._max)
        self._buffers[issue_id].append(event)

    def get(self, issue_id: str, limit: int = 50) -> list[AgentEvent]:
        buf = self._buffers.get(issue_id, deque())
        return list(buf)[-limit:]

    def get_since(self, issue_id: str, since: datetime) -> list[AgentEvent]:
        """Get events after a given timestamp."""
        buf = self._buffers.get(issue_id, deque())
        return [e for e in buf if e.timestamp > since]

    def count(self, issue_id: str) -> int:
        return len(self._buffers.get(issue_id, deque()))

    def clear(self, issue_id: str):
        self._buffers.pop(issue_id, None)
