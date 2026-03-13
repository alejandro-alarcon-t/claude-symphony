"""Tests for workspace.py — SPEC 17.2 Workspace Safety."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_symphony.config import HooksConfig, WorkspaceConfig
from claude_symphony.workspace import (
    WorkspaceResult,
    _branch_name_from_key,
    ensure_workspace,
    remove_workspace,
    run_hook,
    sanitize_key,
)


class TestSanitizeKey:
    def test_alphanumeric_passthrough(self):
        assert sanitize_key("FIC-123") == "FIC-123"

    def test_replaces_slashes(self):
        assert sanitize_key("feat/branch") == "feat_branch"

    def test_replaces_spaces(self):
        assert sanitize_key("my issue") == "my_issue"

    def test_keeps_dots_hyphens_underscores(self):
        assert sanitize_key("v1.2-beta_rc") == "v1.2-beta_rc"

    def test_replaces_special_chars(self):
        result = sanitize_key("a@b#c$d%e")
        assert result == "a_b_c_d_e"

    def test_empty_string(self):
        assert sanitize_key("") == ""

    def test_unicode_chars_replaced(self):
        result = sanitize_key("café")
        assert "é" not in result


class TestBranchNameFromKey:
    def test_prefix(self):
        assert _branch_name_from_key("FIC-1") == "claude-symphony/FIC-1"


class TestEnsureWorkspace:
    @pytest.mark.asyncio
    async def test_creates_new_workspace(self, tmp_path):
        hooks = HooksConfig()
        result = await ensure_workspace(tmp_path, "FIC-1", hooks)
        assert result.created_now is True
        assert result.path.exists()
        assert result.workspace_key == "FIC-1"

    @pytest.mark.asyncio
    async def test_reuses_existing_workspace(self, tmp_path):
        hooks = HooksConfig()
        # Create first
        await ensure_workspace(tmp_path, "FIC-1", hooks)
        # Reuse
        result = await ensure_workspace(tmp_path, "FIC-1", hooks)
        assert result.created_now is False

    @pytest.mark.asyncio
    async def test_path_traversal_prevented_by_sanitization(self, tmp_path):
        """Path traversal is prevented by sanitize_key replacing '..' and '/' with '_'."""
        hooks = HooksConfig()
        result = await ensure_workspace(tmp_path, "../../../etc", hooks)
        # Sanitized key replaces unsafe chars, so path stays under root
        assert result.workspace_key == ".._.._.._etc"
        assert result.path.resolve().is_relative_to(tmp_path.resolve())

    @pytest.mark.asyncio
    async def test_sanitized_key_used(self, tmp_path):
        hooks = HooksConfig()
        result = await ensure_workspace(tmp_path, "FIC/123", hooks)
        assert result.workspace_key == "FIC_123"
        assert (tmp_path / "FIC_123").exists()

    @pytest.mark.asyncio
    async def test_after_create_hook_runs(self, tmp_path):
        marker = tmp_path / "hook_ran"
        hooks = HooksConfig(
            after_create=f"touch {marker}",
            timeout_ms=5000,
        )
        await ensure_workspace(tmp_path, "FIC-2", hooks)
        assert marker.exists()

    @pytest.mark.asyncio
    async def test_after_create_hook_failure_cleans_up(self, tmp_path):
        hooks = HooksConfig(
            after_create="exit 1",
            timeout_ms=5000,
        )
        with pytest.raises(RuntimeError, match="after_create hook failed"):
            await ensure_workspace(tmp_path, "FIC-FAIL", hooks)
        # Workspace should be cleaned up
        assert not (tmp_path / "FIC-FAIL").exists()

    @pytest.mark.asyncio
    async def test_deterministic_paths(self, tmp_path):
        hooks = HooksConfig()
        r1 = await ensure_workspace(tmp_path, "FIC-X", hooks)
        r2 = await ensure_workspace(tmp_path, "FIC-X", hooks)
        assert r1.path == r2.path


class TestRemoveWorkspace:
    @pytest.mark.asyncio
    async def test_removes_directory(self, tmp_path):
        hooks = HooksConfig()
        await ensure_workspace(tmp_path, "FIC-1", hooks)
        assert (tmp_path / "FIC-1").exists()
        await remove_workspace(tmp_path, "FIC-1", hooks)
        assert not (tmp_path / "FIC-1").exists()

    @pytest.mark.asyncio
    async def test_noop_if_not_exists(self, tmp_path):
        hooks = HooksConfig()
        # Should not raise
        await remove_workspace(tmp_path, "FIC-GONE", hooks)

    @pytest.mark.asyncio
    async def test_before_remove_hook_runs(self, tmp_path):
        hooks = HooksConfig()
        await ensure_workspace(tmp_path, "FIC-1", hooks)

        marker = tmp_path / "remove_hook_ran"
        hooks_with_remove = HooksConfig(
            before_remove=f"touch {marker}",
            timeout_ms=5000,
        )
        await remove_workspace(tmp_path, "FIC-1", hooks_with_remove)
        assert marker.exists()


class TestRunHook:
    @pytest.mark.asyncio
    async def test_successful_hook(self, tmp_path):
        result = await run_hook("echo hello", tmp_path, 5000, "test")
        assert result is True

    @pytest.mark.asyncio
    async def test_failed_hook(self, tmp_path):
        result = await run_hook("exit 1", tmp_path, 5000, "test")
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_hook(self, tmp_path):
        result = await run_hook("sleep 10", tmp_path, 100, "test")
        assert result is False

    @pytest.mark.asyncio
    async def test_hook_runs_in_workspace_dir(self, tmp_path):
        marker = tmp_path / "cwd_check"
        # pwd should output tmp_path
        result = await run_hook(f"pwd > {marker}", tmp_path, 5000, "test")
        assert result is True
        assert tmp_path.name in marker.read_text()
