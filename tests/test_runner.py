"""Tests for runner.py — SPEC 17.5 Runner."""

from __future__ import annotations

from pathlib import Path

from claude_symphony.config import ClaudeConfig
from claude_symphony.models import RunAttempt
from claude_symphony.runner import _process_event, build_claude_args, build_codex_args


class TestBuildClaudeArgs:
    def test_first_turn_basic(self):
        cfg = ClaudeConfig(command="claude", permission_mode="auto")
        args = build_claude_args(cfg, "do stuff", Path("/ws"))
        assert args[0] == "claude"
        assert "-p" in args
        assert args[args.index("-p") + 1] == "do stuff"
        assert "--verbose" in args
        assert "--output-format" in args
        assert "stream-json" in args
        assert "--resume" not in args

    def test_continuation_turn_includes_resume(self):
        cfg = ClaudeConfig(command="claude")
        args = build_claude_args(cfg, "continue", Path("/ws"), session_id="sess-123")
        assert "--resume" in args
        assert args[args.index("--resume") + 1] == "sess-123"

    def test_first_turn_includes_system_prompt(self):
        cfg = ClaudeConfig(command="claude")
        args = build_claude_args(cfg, "prompt", Path("/ws"))
        assert "--append-system-prompt" in args
        idx = args.index("--append-system-prompt")
        system_prompt = args[idx + 1]
        assert "headless" in system_prompt.lower()
        assert "Do NOT use interactive skills" in system_prompt

    def test_continuation_turn_no_system_prompt(self):
        cfg = ClaudeConfig(command="claude")
        args = build_claude_args(cfg, "prompt", Path("/ws"), session_id="s")
        assert "--append-system-prompt" not in args

    def test_custom_system_prompt_appended(self):
        cfg = ClaudeConfig(
            command="claude", append_system_prompt="Custom instruction"
        )
        args = build_claude_args(cfg, "prompt", Path("/ws"))
        idx = args.index("--append-system-prompt")
        assert "Custom instruction" in args[idx + 1]

    def test_auto_permission_mode(self):
        cfg = ClaudeConfig(command="claude", permission_mode="auto")
        args = build_claude_args(cfg, "p", Path("/ws"))
        assert "--permission-mode" in args
        assert args[args.index("--permission-mode") + 1] == "auto"

    def test_allowed_tools_permission_mode(self):
        cfg = ClaudeConfig(
            command="claude",
            permission_mode="allowedTools",
            allowed_tools=["Bash", "Read"],
        )
        args = build_claude_args(cfg, "p", Path("/ws"))
        assert "--allowedTools" in args
        assert args[args.index("--allowedTools") + 1] == "Bash,Read"

    def test_model_override(self):
        cfg = ClaudeConfig(command="claude", model="opus")
        args = build_claude_args(cfg, "p", Path("/ws"))
        assert "--model" in args
        assert args[args.index("--model") + 1] == "opus"

    def test_no_model_when_none(self):
        cfg = ClaudeConfig(command="claude", model=None)
        args = build_claude_args(cfg, "p", Path("/ws"))
        assert "--model" not in args

    def test_custom_command(self):
        cfg = ClaudeConfig(command="/usr/local/bin/claude")
        args = build_claude_args(cfg, "p", Path("/ws"))
        assert args[0] == "/usr/local/bin/claude"


class TestBuildCodexArgs:
    def test_basic(self):
        args = build_codex_args(None, "do stuff", Path("/ws"))
        assert args[0] == "codex"
        assert "--quiet" in args
        assert "--prompt" in args
        assert args[args.index("--prompt") + 1] == "do stuff"

    def test_with_model(self):
        args = build_codex_args("gpt-4", "prompt", Path("/ws"))
        assert "--model" in args
        assert args[args.index("--model") + 1] == "gpt-4"

    def test_without_model(self):
        args = build_codex_args(None, "prompt", Path("/ws"))
        assert "--model" not in args


class TestProcessEvent:
    def _make_attempt(self) -> RunAttempt:
        return RunAttempt(issue_id="id", issue_identifier="FIC-1")

    def test_result_event_extracts_session_id(self):
        attempt = self._make_attempt()
        event = {
            "type": "result",
            "session_id": "sess-abc",
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            "result": "Done",
        }
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.session_id == "sess-abc"
        assert attempt.input_tokens == 100
        assert attempt.output_tokens == 50
        assert attempt.total_tokens == 150
        assert attempt.last_message == "Done"

    def test_result_event_without_session_id(self):
        attempt = self._make_attempt()
        event = {"type": "result", "usage": {}, "result": ""}
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.session_id is None

    def test_result_event_total_tokens_fallback(self):
        attempt = self._make_attempt()
        event = {
            "type": "result",
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 0},
        }
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.total_tokens == 150  # input + output

    def test_assistant_event_string_content(self):
        attempt = self._make_attempt()
        event = {"type": "assistant", "message": {"content": "Thinking..."}}
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.last_message == "Thinking..."

    def test_assistant_event_list_content(self):
        attempt = self._make_attempt()
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Block 1"},
                    {"type": "text", "text": "Block 2"},
                ]
            },
        }
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.last_message == "Block 1"

    def test_tool_use_event(self):
        attempt = self._make_attempt()
        event = {"type": "tool_use", "name": "Bash"}
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.last_message == "Using tool: Bash"

    def test_tool_use_event_with_tool_field(self):
        attempt = self._make_attempt()
        event = {"type": "tool_use", "tool": "Read"}
        _process_event(event, attempt, None, "FIC-1")
        assert attempt.last_message == "Using tool: Read"

    def test_last_event_type_set(self):
        attempt = self._make_attempt()
        _process_event({"type": "assistant", "message": {"content": "hi"}}, attempt, None, "FIC-1")
        assert attempt.last_event == "assistant"

    def test_callback_invoked(self):
        attempt = self._make_attempt()
        calls = []
        _process_event(
            {"type": "result", "session_id": "s", "usage": {}, "result": ""},
            attempt,
            lambda ident, etype, ev: calls.append((ident, etype)),
            "FIC-1",
        )
        assert len(calls) == 1
        assert calls[0] == ("FIC-1", "result")

    def test_truncates_long_messages(self):
        attempt = self._make_attempt()
        event = {"type": "result", "usage": {}, "result": "x" * 500}
        _process_event(event, attempt, None, "FIC-1")
        assert len(attempt.last_message) == 200
