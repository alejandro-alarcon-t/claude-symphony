#!/usr/bin/env python3
"""Quick preview of the Claude Symphony dashboard with mock data.

Usage: python preview_dashboard.py [port]
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from collections import deque


# Mock orchestrator that returns realistic demo data
class MockOrchestrator:
    def __init__(self):
        self._start = datetime.now(timezone.utc)
        self._events = self._make_events()

    def _make_events(self):
        """Generate realistic mock events."""
        now = datetime.now(timezone.utc)
        events = []
        samples = [
            ("thinking", "Analyzing the codebase structure to understand where authentication middleware is defined..."),
            ("tool_use", "Grep: auth.*middleware", "Grep"),
            ("tool_result", "Found 3 matches in src/middleware/auth.ts, src/routes/api.ts, src/config/security.ts"),
            ("thinking", "I can see the auth middleware is defined in src/middleware/auth.ts. Let me read it to understand the current implementation."),
            ("tool_use", "Read: src/middleware/auth.ts", "Read"),
            ("tool_result", "File contents: export function authMiddleware(req, res, next) { ... } — 47 lines"),
            ("thinking", "The current implementation uses session tokens stored in cookies. I need to migrate to JWT tokens with proper refresh handling."),
            ("tool_use", "Edit: src/middleware/auth.ts", "Edit"),
            ("tool_result", "File updated successfully"),
            ("tool_use", "Bash: npm test -- --grep 'auth'", "Bash"),
            ("tool_result", "14/14 tests passing"),
            ("thinking", "All auth tests pass. Now I need to update the API routes to use the new JWT validation."),
            ("tool_use", "Read: src/routes/api.ts", "Read"),
            ("tool_result", "File contents: import { authMiddleware } from '../middleware/auth' — 124 lines"),
            ("tool_use", "Edit: src/routes/api.ts", "Edit"),
            ("tool_result", "File updated — added JWT validation to 6 endpoints"),
            ("tool_use", "Bash: npm test", "Bash"),
            ("thinking", "Tests are running... let me check the results"),
            ("result", "All 42 tests passing. Authentication migration complete."),
        ]
        for i, s in enumerate(samples):
            ts = now - timedelta(seconds=(len(samples) - i) * 15)
            evt = {
                "timestamp": ts.isoformat(),
                "event_type": s[0],
                "summary": s[1],
                "detail": s[1] if len(s[1]) > 100 else None,
                "tool_name": s[2] if len(s) > 2 else None,
            }
            events.append(evt)
        return {"demo-issue-1": events}

    def get_state_snapshot(self):
        now = datetime.now(timezone.utc)
        elapsed = (now - self._start).total_seconds()
        return {
            "generated_at": now.isoformat(),
            "counts": {"running": 3, "retrying": 1, "gates": 1},
            "running": [
                {
                    "issue_id": "demo-issue-1",
                    "issue_identifier": "SYM-42",
                    "issue_title": "Add JWT authentication to API endpoints",
                    "issue_url": "https://linear.app/demo/issue/SYM-42",
                    "issue_labels": ["backend", "auth", "security"],
                    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "turn_count": 3,
                    "status": "streaming",
                    "last_event": "tool_use",
                    "last_message": "Running test suite: npm test -- --grep 'auth'",
                    "started_at": (now - timedelta(minutes=12)).isoformat(),
                    "last_event_at": (now - timedelta(seconds=5)).isoformat(),
                    "tokens": {"input_tokens": 45200, "output_tokens": 12800, "total_tokens": 58000},
                    "state_name": "implement",
                    "event_count": 17,
                    "pid": 12345,
                    "workspace_path": "/tmp/workspaces/SYM-42",
                },
                {
                    "issue_id": "demo-issue-2",
                    "issue_identifier": "SYM-38",
                    "issue_title": "Fix token refresh race condition in concurrent requests",
                    "issue_url": "https://linear.app/demo/issue/SYM-38",
                    "issue_labels": ["bug", "critical"],
                    "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                    "turn_count": 5,
                    "status": "streaming",
                    "last_event": "assistant",
                    "last_message": "Investigating the mutex implementation in the token refresh handler...",
                    "started_at": (now - timedelta(minutes=25)).isoformat(),
                    "last_event_at": (now - timedelta(seconds=2)).isoformat(),
                    "tokens": {"input_tokens": 89400, "output_tokens": 31200, "total_tokens": 120600},
                    "state_name": "investigate",
                    "event_count": 34,
                    "pid": 12346,
                    "workspace_path": "/tmp/workspaces/SYM-38",
                },
                {
                    "issue_id": "demo-issue-5",
                    "issue_identifier": "SYM-51",
                    "issue_title": "Migrate database schema for multi-tenant support",
                    "issue_url": "https://linear.app/demo/issue/SYM-51",
                    "issue_labels": ["database", "migration"],
                    "session_id": "e5f6a7b8-c9d0-1234-efgh-567890123456",
                    "turn_count": 1,
                    "status": "paused",
                    "last_event": "tool_use",
                    "last_message": "Paused while reviewing migration plan",
                    "started_at": (now - timedelta(minutes=8)).isoformat(),
                    "last_event_at": (now - timedelta(minutes=3)).isoformat(),
                    "tokens": {"input_tokens": 15600, "output_tokens": 4200, "total_tokens": 19800},
                    "state_name": "implement",
                    "event_count": 8,
                    "pid": 12349,
                    "workspace_path": "/tmp/workspaces/SYM-51",
                },
            ],
            "retrying": [
                {
                    "issue_id": "demo-issue-3",
                    "issue_identifier": "SYM-45",
                    "issue_title": "Add rate limiting to public API endpoints",
                    "issue_url": "https://linear.app/demo/issue/SYM-45",
                    "attempt": 2,
                    "error": "Turn timeout after 3600s — agent stalled on npm install",
                },
            ],
            "gates": [
                {
                    "issue_id": "demo-issue-4",
                    "issue_identifier": "SYM-33",
                    "issue_title": "Refactor user service to use repository pattern",
                    "issue_url": "https://linear.app/demo/issue/SYM-33",
                    "gate_state": "code-review",
                    "run": 2,
                },
            ],
            "totals": {
                "input_tokens": 234500,
                "output_tokens": 78900,
                "total_tokens": 313400,
                "seconds_running": round(elapsed + 1847.3, 1),
            },
        }

    def get_events(self, issue_id, limit=50):
        events = self._events.get(issue_id, [])
        return events[-limit:]

    async def pause_agent(self, issue_id):
        print(f"[mock] Pause agent: {issue_id}")
        return True

    async def resume_agent(self, issue_id):
        print(f"[mock] Resume agent: {issue_id}")
        return True

    async def stop_agent(self, issue_id):
        print(f"[mock] Stop agent: {issue_id}")
        return True

    async def _tick(self):
        print("[mock] Force refresh tick")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4200

    try:
        import uvicorn
    except ImportError:
        print("Install uvicorn: pip install uvicorn")
        sys.exit(1)

    from claude_symphony.web import create_app

    orch = MockOrchestrator()
    app = create_app(orch)

    print(f"\n  CLAUDE SYMPHONY — Dashboard Preview")
    print(f"  http://127.0.0.1:{port}\n")
    print(f"  Mock data: 3 running, 1 retrying, 1 gate")
    print(f"  Press Ctrl+C to stop\n")

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
