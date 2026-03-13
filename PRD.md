# PRD: Claude Symphony Dashboard v2

**Author:** Claude Symphony team
**Date:** 2026-03-13
**Status:** Draft
**Design reference:** `ui.pen` (Pencil file with annotated mockups)

---

## 1. Vision

Transform the Claude Symphony web dashboard from a passive status display into an **interactive command center** for monitoring and controlling autonomous agents. Operators should be able to observe agent thinking in real-time, intervene when needed, and understand at a glance what every agent is doing and why.

---

## 2. Current State

The existing dashboard (`web.py`) is a single inline HTML page served by FastAPI. It polls `/api/v1/state` every 3 seconds and renders agent cards with basic info: identifier, status pill, last message, token count, and turn number.

### What works
- Clean dark terminal aesthetic, sharp corners, IBM Plex Mono
- Metrics row showing running/queued/tokens/runtime
- Auto-refresh with status dot indicator

### What doesn't
- **No issue titles** — cards only show `FIC-42`, not what the issue is about
- **No event visibility** — `last_message` is a single truncated string; there's no history of what the agent has been thinking, reading, or doing
- **No controls** — operators cannot pause, resume, or stop individual agents from the dashboard; they must change the Linear state manually
- **Stats bar is noisy** — the animated progress bar and IN/OUT breakdown distract from agent cards without adding value
- **No click interaction** — cards are purely visual; clicking does nothing
- **Polling only** — 3-second poll creates a laggy feel for real-time monitoring
- **No issue context** — no link to Linear, no labels, no parent/epic info

---

## 3. Requirements

### P0 — Must ship

#### 3.1 Issue titles in agent cards
Show the issue title prominently on every card. The identifier alone is not enough for operators managing multiple agents.

- **Data source:** `Issue.title` is already fetched by the orchestrator and cached in `_last_issues`. Currently not exposed in `get_state_snapshot()`.
- **Card layout change:** Title appears as the first line in the card's content area (above the status pill row).
- **Truncation:** Titles longer than ~80 characters should be truncated with ellipsis. Full title visible in the detail panel.

#### 3.2 Expandable detail panel (Activity Log)
Clicking an agent card expands it to reveal a scrollable activity log showing recent events from the agent's stream-json output.

**Event types to display:**

| Badge | Color | Source | Content shown |
|-------|-------|--------|---------------|
| `THINKING` | Amber | `assistant` events with text content | Truncated thinking/reasoning text |
| `TOOL` | Blue | `tool_use` events | Tool name + key input (e.g., file path, command) |
| `RESULT` | Green | `tool_result` or significant `assistant` messages | Output summary |
| `ERROR` | Red | Failed tool results or error events | Error message |

**Each log entry shows:**
- Timestamp (HH:MM:SS)
- Event type badge (color-coded)
- Content text (truncated to 1-2 lines, expandable on click)

**Backend requirement:** The orchestrator must buffer recent events per issue. Currently `_process_event()` only updates `last_message` and `last_event` on the `RunAttempt`. We need a ring buffer of the last N events per issue.

**Behavior:**
- Only one card can be expanded at a time
- Expanding a card scrolls it into view if needed
- The log auto-scrolls to the latest entry while expanded
- A `✕` button or clicking the card header again collapses it
- Selected card gets an amber left border indicator
- The detail panel lives visually below the card row, within the agents list container

#### 3.3 Pause / Resume / Stop controls
Operators need to control individual agents without leaving the dashboard.

**Pause (running agents):**
- Sends `SIGSTOP` to the agent's process group, freezing execution
- Status changes to `paused`
- Pause button (`⏸`) becomes a Resume button (`▶`)
- Agent card shows `PAUSED` pill (new status variant, dim amber or grey)
- The paused agent does NOT release its concurrency slot (it's still "running", just frozen)

**Resume (paused agents):**
- Sends `SIGCONT` to the agent's process group
- Status returns to `streaming`
- Resume button becomes Pause button again

**Stop (running or retrying agents):**
- Kills the agent process (same as current reconciliation cancel)
- Releases the concurrency slot
- Does NOT move the Linear issue state (operator decides what to do)
- Confirmation modal: "Stop agent for FIC-42? The issue will remain in its current Linear state."

**API endpoints needed:**
```
POST /api/v1/{issue_id}/pause
POST /api/v1/{issue_id}/resume
POST /api/v1/{issue_id}/stop
```

**Button placement:** Top of the right-hand meta column on each card. `⏸` for LIVE cards, `⏹` for RETRYING cards. Gate cards show no control buttons.

#### 3.4 Remove stats bar
Delete the IN/OUT token stats bar and the animated progress bar from the footer area. The metrics row already shows total tokens. The progress bar's constant animation is distracting and conveys no useful information.

### P1 — Should ship

#### 3.5 WebSocket for real-time updates
Replace the 3-second polling with a WebSocket connection for instant updates.

- **Endpoint:** `ws://host:port/ws`
- **Protocol:** Server pushes the full state snapshot on every event change (debounced to max 2 updates/second)
- **Fallback:** If WebSocket fails to connect, fall back to 3-second polling (current behavior)
- **Event-level streaming:** For the expanded detail panel, the WebSocket should push individual events for the selected issue in real-time, not just snapshot refreshes

**Implementation:** FastAPI supports WebSocket natively. The orchestrator's `_on_agent_event` callback is the ideal hook point — it already receives every NDJSON event. Add a WebSocket broadcast there.

#### 3.6 Issue context in cards and detail panel
Surface more Linear context to help operators understand what they're looking at.

**In the card:**
- Issue title (P0, covered above)
- State machine state name (already shown as `implement`, `investigate`, etc.)

**In the detail panel (expanded):**
- Link to Linear issue (clickable URL)
- Labels (as small pills)
- Parent/epic identifier and title (if exists)
- Sibling issues and their states (context for multi-part work)
- Run number and rework count
- Session ID (for debugging)
- Workspace path

**Data source:** Most of this is already in `_last_issues`. The `Issue` model has `url`, `labels`, `parent`, `siblings`. The `RunAttempt` has `session_id`, `workspace_path`, `state_name`. The orchestrator has `_issue_state_runs`.

#### 3.7 Keyboard shortcuts
Power users should be able to navigate entirely by keyboard.

| Key | Action |
|-----|--------|
| `j` / `k` | Move selection up/down through agent cards |
| `Enter` / `Space` | Toggle expand/collapse on selected card |
| `p` | Pause/resume selected agent |
| `s` | Stop selected agent (with confirmation) |
| `Escape` | Collapse expanded card / dismiss modal |
| `r` | Force refresh |
| `?` | Show keyboard shortcut overlay |

#### 3.8 Browser notifications for gate states
When an agent enters a gate (awaiting human review), show a browser notification if the tab is not focused.

- Request `Notification.permission` on first load
- Trigger on gate entry: "FIC-42 is awaiting review at research-review"
- Optional: play a subtle sound

#### 3.9 Agent card sorting and filtering
As the number of agents grows, operators need to find specific ones quickly.

- **Sort by:** Status (streaming first, then gates, then retrying), priority, identifier, runtime
- **Filter by:** Status type, state machine state, search by identifier/title
- **Sticky:** Expanded card stays visible even if sort order changes

### P2 — Nice to have

#### 3.10 State machine visualization
Show the workflow state machine as an interactive diagram in a collapsible sidebar or modal.

- Parse `states` from the config to render nodes and edges
- Highlight the current state for each active issue
- Show transition paths and gate requirements
- Use SVG or Canvas rendering (no external dependencies)

#### 3.11 Token cost estimation
Show estimated cost alongside token counts.

- Configurable price per 1K tokens (input vs output, varies by model)
- Show per-agent cost in the detail panel
- Show cumulative cost in the metrics row
- Config: `server.cost_per_1k_input`, `server.cost_per_1k_output` in workflow.yaml

#### 3.12 Dark / light theme toggle
The current dark theme is great for extended monitoring. Offer a light theme for daytime use.

- Toggle in the header
- Persist preference in `localStorage`
- CSS custom properties already make this straightforward

#### 3.13 Log export
Download the activity log for a specific agent as a text file.

- Button in the detail panel header
- Format: timestamped plaintext
- Useful for debugging and post-mortems

#### 3.14 Multi-dashboard / multi-workflow
Support monitoring multiple workflow instances from a single dashboard.

- Tabs or workspace switcher in the header
- Each tab connects to a different orchestrator instance
- Useful for teams running multiple projects

---

## 4. Technical Architecture

### 4.1 Event Buffer System (Backend — new)

The core backend change is an event buffer that captures the NDJSON stream per issue.

```python
# New in orchestrator.py or a dedicated events.py

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentEvent:
    """A single event from the agent's stream-json output."""
    timestamp: datetime
    event_type: str          # "thinking", "tool_use", "tool_result", "error", "result"
    summary: str             # Human-readable one-liner
    detail: str | None = None  # Full content (for expand-on-click)
    tool_name: str | None = None
    tool_input: str | None = None


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

    def clear(self, issue_id: str):
        self._buffers.pop(issue_id, None)
```

**Integration points:**

1. `runner.py` `_process_event()` — classify each NDJSON event and push to the buffer
2. `orchestrator.py` `_on_agent_event()` — forward to WebSocket broadcast
3. `orchestrator.py` `_on_worker_exit()` — keep buffer (don't clear on success, only on terminal cleanup)

**Event classification logic** (in `_process_event`):

```python
def _classify_event(event: dict) -> AgentEvent | None:
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
        tool = event.get("name", "")
        inp = event.get("input", {})
        # Extract the most relevant input field
        preview = _tool_input_preview(tool, inp)
        return AgentEvent(
            timestamp=now,
            event_type="tool_use",
            summary=f"{tool}: {preview}",
            tool_name=tool,
            tool_input=json.dumps(inp)[:500] if inp else None,
        )

    elif etype == "tool_result":
        content = _extract_text(event)
        return AgentEvent(
            timestamp=now,
            event_type="tool_result",
            summary=content[:200] if content else "Done",
            detail=content if content and len(content) > 200 else None,
        )

    elif etype == "result":
        return AgentEvent(
            timestamp=now,
            event_type="result",
            summary=event.get("result", "")[:200],
        )

    return None
```

### 4.2 Pause / Resume System (Backend — new)

Pause/resume leverages Unix signals to freeze/unfreeze the Claude subprocess.

```python
# New methods in orchestrator.py

async def pause_agent(self, issue_id: str) -> bool:
    """Pause a running agent by sending SIGSTOP to its process group."""
    if issue_id not in self.running:
        return False
    attempt = self.running[issue_id]
    # Find the child PID for this issue
    for pid in self._child_pids:
        try:
            os.killpg(os.getpgid(pid), signal.SIGSTOP)
            attempt.status = "paused"
            return True
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return False

async def resume_agent(self, issue_id: str) -> bool:
    """Resume a paused agent by sending SIGCONT."""
    attempt = self.running.get(issue_id)
    if not attempt or attempt.status != "paused":
        return False
    for pid in self._child_pids:
        try:
            os.killpg(os.getpgid(pid), signal.SIGCONT)
            attempt.status = "streaming"
            return True
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return False

async def stop_agent(self, issue_id: str) -> bool:
    """Stop a running or retrying agent."""
    # Cancel async task
    task = self._tasks.get(issue_id)
    if task:
        task.cancel()
    # Kill process
    # ... (reuse existing PID kill logic)
    # Release slot
    self.running.pop(issue_id, None)
    self._tasks.pop(issue_id, None)
    self.claimed.discard(issue_id)
    # Cancel pending retry
    if issue_id in self._retry_timers:
        self._retry_timers[issue_id].cancel()
        self._retry_timers.pop(issue_id, None)
    self.retry_attempts.pop(issue_id, None)
    return True
```

**Important:** The stall detector must account for paused state — a paused agent should not be killed for stalling. Add a check in the `stall_monitor()` coroutine:

```python
if attempt.status == "paused":
    last_activity = loop.time()  # reset stall timer
    continue
```

**PID-to-issue mapping:** Currently `_child_pids` is a flat set with no issue mapping. We need to change it to `dict[int, str]` (pid → issue_id) so we can target the right PID for pause/resume. This also requires updating `_on_child_pid` and the shutdown logic.

### 4.3 API Changes (Backend)

#### Modified endpoints

**`GET /api/v1/state`** — Add issue titles and event counts to the snapshot:

```json
{
  "running": [
    {
      "issue_id": "...",
      "issue_identifier": "FIC-42",
      "issue_title": "Add user authentication to API endpoints",
      "issue_url": "https://linear.app/...",
      "issue_labels": ["backend", "auth"],
      "state_name": "implement",
      "status": "streaming",
      "event_count": 47,
      ...existing fields...
    }
  ],
  "gates": [
    {
      ...existing fields...,
      "issue_title": "Investigate token refresh race condition",
      "issue_url": "https://linear.app/..."
    }
  ]
}
```

#### New endpoints

```
GET  /api/v1/{issue_id}/events?limit=50&since=<timestamp>
     → Returns recent events from the buffer for this issue
     → Used by the detail panel on first expand

POST /api/v1/{issue_id}/pause   → Pause agent
POST /api/v1/{issue_id}/resume  → Resume agent
POST /api/v1/{issue_id}/stop    → Stop agent (kills process, releases slot)

WS   /ws
     → WebSocket for real-time state + event streaming
     → Client sends: {"subscribe": "FIC-42"} to receive per-event updates
     → Client sends: {"unsubscribe": "FIC-42"} to stop
     → Server sends: {"type": "snapshot", "data": {...}} on state changes
     → Server sends: {"type": "event", "issue_id": "...", "event": {...}} for subscribed issues
```

### 4.4 Frontend Architecture

The current inline HTML+JS is reaching its limit. For this iteration, we keep the zero-dependency approach (no React, no build step) but restructure the JS into clear modules.

#### Component structure (all inline in `web.py`)

```
HTML
├── <header>           (unchanged)
├── <div.metrics>      (unchanged)
├── <div.section-header> (unchanged)
├── <div#agents-container>
│   ├── .agent-card    (updated: clickable, title, controls)
│   ├── .detail-panel  (new: activity log, issue context)
│   └── ...more cards
├── <footer>           (simplified: no stats bar)
├── <div#confirm-modal> (new: stop confirmation)
└── <div#shortcuts-overlay> (new: keyboard help)

JS modules (IIFE pattern):
├── state.js      — WebSocket/polling state management
├── cards.js      — Agent card rendering
├── detail.js     — Detail panel rendering + event log
├── controls.js   — Pause/resume/stop handlers
├── keyboard.js   — Keyboard shortcut handler
└── notify.js     — Browser notification manager
```

#### Detail panel HTML structure

```html
<div class="detail-panel" data-issue-id="...">
  <div class="detail-header">
    <span class="detail-label">ACTIVITY LOG</span>
    <div class="detail-line"></div>
    <button class="detail-close">✕</button>
  </div>
  <div class="detail-context">
    <!-- Issue metadata: link, labels, parent, siblings, session -->
  </div>
  <div class="detail-log">
    <div class="log-entry">
      <span class="log-ts">14:32:01</span>
      <span class="log-badge result">RESULT</span>
      <span class="log-msg">npm test completed — 14/14 passing</span>
    </div>
    <div class="log-entry">
      <span class="log-ts">14:31:45</span>
      <span class="log-badge thinking">THINKING</span>
      <span class="log-msg">All 14 tests pass. Now adding JWT auth...</span>
    </div>
    <!-- ... -->
  </div>
</div>
```

#### CSS additions

```css
/* Selected card */
.agent-card.selected {
  border-left: 2px solid var(--amber);
}

/* Detail panel */
.detail-panel {
  background: var(--surface);
  padding: 0 24px 20px;
  max-height: 400px;
  overflow-y: auto;
  animation: slideDown 0.15s ease-out;
}

@keyframes slideDown {
  from { max-height: 0; opacity: 0; }
  to   { max-height: 400px; opacity: 1; }
}

/* Log entries */
.log-entry { display: flex; gap: 12px; padding: 8px 0; align-items: start; }
.log-ts    { width: 64px; color: var(--dim); font-size: 11px; flex-shrink: 0; }
.log-badge { width: 64px; text-align: center; font-size: 9px; font-weight: 500;
             padding: 1px 6px; flex-shrink: 0; letter-spacing: 0.08em; }

.log-badge.thinking { background: rgba(232,184,75,0.08); color: var(--amber);
                      border: 1px solid var(--amber-dim); }
.log-badge.tool_use { background: rgba(91,156,246,0.1); color: var(--blue);
                      border: 1px solid rgba(91,156,246,0.25); }
.log-badge.result,
.log-badge.tool_result { background: rgba(76,186,110,0.1); color: var(--green);
                         border: 1px solid rgba(76,186,110,0.25); }
.log-badge.error   { background: rgba(217,95,82,0.1); color: var(--red);
                     border: 1px solid rgba(217,95,82,0.25); }

/* Pause/stop controls */
.agent-control {
  padding: 3px 10px;
  border: 1px solid var(--amber-dim);
  background: rgba(232,184,75,0.08);
  color: var(--amber);
  font-family: var(--font);
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s;
}
.agent-control:hover { background: rgba(232,184,75,0.2); }
.agent-control.stop  { border-color: rgba(91,156,246,0.25);
                       background: rgba(91,156,246,0.1); color: var(--blue); }

/* Paused status pill */
.status-pill.paused {
  background: rgba(85,85,80,0.15);
  color: var(--muted);
  border: 1px solid var(--border-hi);
}
```

---

## 5. Data Model Changes

### 5.1 RunAttempt additions

```python
@dataclass
class RunAttempt:
    # ... existing fields ...
    pid: int | None = None           # Track the specific PID for this attempt
```

### 5.2 Orchestrator additions

```python
class Orchestrator:
    def __init__(self, ...):
        # ... existing ...
        self._event_buffer: EventBuffer = EventBuffer(max_events=200)
        self._child_pid_map: dict[int, str] = {}   # pid → issue_id (replaces _child_pids set)
        self._ws_clients: set[WebSocket] = set()    # active WebSocket connections
        self._ws_subscriptions: dict[WebSocket, str | None] = {}  # ws → subscribed issue_id
```

### 5.3 State snapshot additions

Add to `get_state_snapshot()`:

```python
# In each running entry:
"issue_title": self._last_issues.get(r.issue_id, ...).title,
"issue_url": self._last_issues.get(r.issue_id, ...).url,
"issue_labels": self._last_issues.get(r.issue_id, ...).labels,
"event_count": len(self._event_buffer.get(r.issue_id)),
"pid": r.pid,

# In each gate entry:
"issue_title": ...,
"issue_url": ...,
```

---

## 6. Implementation Plan

### Phase 1: Data layer (backend only)
1. Add `EventBuffer` class and `AgentEvent` dataclass
2. Update `_process_event()` to classify events and push to buffer
3. Change `_child_pids: set` to `_child_pid_map: dict[int, str]`
4. Add `issue_title`, `issue_url`, `issue_labels`, `event_count` to state snapshot
5. Add `GET /api/v1/{issue_id}/events` endpoint

### Phase 2: Controls (backend + minimal frontend)
6. Implement `pause_agent()`, `resume_agent()`, `stop_agent()`
7. Add `paused` status handling in stall detector and reconciliation
8. Add `POST` control endpoints
9. Add control buttons to the frontend cards

### Phase 3: Frontend overhaul
10. Add issue titles to card rendering
11. Remove stats bar HTML/CSS/JS
12. Implement clickable cards with expand/collapse
13. Implement detail panel with activity log rendering
14. Implement issue context section in detail panel
15. Add confirmation modal for stop action
16. Add `paused` status pill variant

### Phase 4: Real-time (WebSocket)
17. Add WebSocket endpoint to FastAPI app
18. Broadcast state snapshots on change (debounced)
19. Support per-issue event subscriptions
20. Update frontend to prefer WebSocket, fall back to polling

### Phase 5: Polish
21. Keyboard shortcuts
22. Browser notifications for gates
23. Smooth expand/collapse animations
24. Auto-scroll in activity log

---

## 7. Event Classification Reference

How NDJSON events from Claude Code map to dashboard events:

| stream-json `type` | Dashboard badge | Summary extraction |
|---|---|---|
| `assistant` (with text content) | `THINKING` | First 200 chars of text content |
| `tool_use` with `name: "Bash"` | `TOOL` | `Bash: {command}` (truncated) |
| `tool_use` with `name: "Read"` | `TOOL` | `Read: {file_path}` |
| `tool_use` with `name: "Edit"` | `TOOL` | `Edit: {file_path}` |
| `tool_use` with `name: "Write"` | `TOOL` | `Write: {file_path}` |
| `tool_use` with `name: "Grep"` | `TOOL` | `Grep: "{pattern}"` |
| `tool_use` with `name: "Glob"` | `TOOL` | `Glob: {pattern}` |
| `tool_use` (other) | `TOOL` | `{tool_name}` |
| `tool_result` (success) | `RESULT` | First 200 chars of output |
| `tool_result` (error) | `ERROR` | Error message |
| `result` | `RESULT` | Final result text |

### Tool input preview extraction

For each tool, extract the most informative field for the one-line summary:

```python
_TOOL_PREVIEW_FIELDS = {
    "Bash": "command",
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "Grep": "pattern",
    "Glob": "pattern",
    "Agent": "prompt",     # first 100 chars
    "WebSearch": "query",
    "WebFetch": "url",
}
```

---

## 8. Open Questions

1. **Event buffer persistence:** Should we persist the event buffer to disk for crash recovery, or is in-memory sufficient? Current lean: in-memory is fine — events are ephemeral debugging context, not business data.

2. **Pause semantics with multi-turn:** If an agent is paused mid-turn and the turn timeout fires, should we honor the timeout or extend it? Current lean: extend — paused time should not count against the turn timeout.

3. **WebSocket authentication:** The current dashboard has no auth. Should the WebSocket require a token? Current lean: no auth for v1 (same as the REST API), add auth as a separate feature.

4. **Event buffer size per issue:** 200 events is roughly the last 5-10 minutes of active agent work. Is this enough? Should it be configurable?

5. **Stop vs Cancel semantics:** Should "stop" from the dashboard post a comment on the Linear issue? Current lean: no — stopping from the dashboard is a local action. The operator can then manually update the Linear issue as they see fit.

6. **Frontend framework migration:** The inline HTML approach works for this iteration, but if the dashboard grows significantly (state machine visualization, multi-workflow), we should consider extracting it into a lightweight framework (Preact, Lit, or even vanilla web components). Not needed now.

---

## 9. Success Metrics

- **Time to understand agent state:** Operators should know what any agent is doing within 2 seconds of looking at the dashboard (issue title + activity log)
- **Time to intervene:** Pause/stop should be a single click, not a context switch to Linear
- **Event latency:** With WebSocket, events should appear in the log within 500ms of occurring
- **Zero new dependencies:** Frontend remains dependency-free (no npm, no build step)
