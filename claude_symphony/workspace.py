"""Workspace management - create, reuse, and clean per-issue workspaces."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import HooksConfig, WorkspaceConfig

logger = logging.getLogger("claude_symphony.workspace")


def sanitize_key(identifier: str) -> str:
    """Replace non-safe chars with underscore for directory name."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", identifier)


@dataclass
class WorkspaceResult:
    path: Path
    workspace_key: str
    created_now: bool


async def run_hook(script: str, cwd: Path, timeout_ms: int, label: str) -> bool:
    """Run a shell hook script in the workspace directory. Returns True on success."""
    logger.info(f"hook={label} cwd={cwd}")
    try:
        proc = await asyncio.create_subprocess_shell(
            script,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_ms / 1000
        )
        if proc.returncode != 0:
            logger.error(
                f"hook={label} failed rc={proc.returncode} stderr={stderr.decode()[:500]}"
            )
            return False
        return True
    except (asyncio.TimeoutError, TimeoutError):
        logger.error(f"hook={label} timed out after {timeout_ms}ms")
        proc.kill()
        return False
    except Exception as e:
        logger.error(f"hook={label} error: {e}")
        return False


def _branch_name_from_key(key: str) -> str:
    """Generate a worktree branch name from issue key."""
    return f"claude-symphony/{key}"


async def _create_worktree(
    repo_path: Path,
    ws_path: Path,
    branch_name: str,
    base_ref: str,
    timeout_ms: int,
) -> bool:
    """Create a git worktree for the given branch from base_ref."""
    # Fetch latest from remote first
    fetch_proc = await asyncio.create_subprocess_exec(
        "git", "fetch", "origin",
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait_for(fetch_proc.communicate(), timeout=timeout_ms / 1000)

    # Create worktree with a new branch from base_ref
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", "-b", branch_name, str(ws_path), base_ref,
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
    if proc.returncode != 0:
        logger.error(f"worktree add failed: {stderr.decode()[:500]}")
        return False
    logger.info(f"Created worktree branch={branch_name} at {ws_path}")
    return True


async def _remove_worktree(repo_path: Path, ws_path: Path, branch_name: str) -> None:
    """Remove a git worktree and its branch."""
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "remove", "--force", str(ws_path),
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait_for(proc.communicate(), timeout=30)

    # Delete local branch
    proc = await asyncio.create_subprocess_exec(
        "git", "branch", "-D", branch_name,
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait_for(proc.communicate(), timeout=10)

    logger.info(f"Removed worktree and branch={branch_name}")


async def ensure_workspace(
    workspace_root: Path,
    issue_identifier: str,
    hooks: HooksConfig,
    ws_config: WorkspaceConfig | None = None,
) -> WorkspaceResult:
    """Create or reuse a workspace for an issue."""
    key = sanitize_key(issue_identifier)
    ws_path = workspace_root / key

    # Safety: workspace must be under root
    ws_abs = ws_path.resolve()
    root_abs = workspace_root.resolve()
    if not ws_abs.is_relative_to(root_abs):
        raise ValueError(f"Workspace path {ws_abs} escapes root {root_abs}")

    created_now = not ws_path.exists()

    if created_now:
        use_worktree = ws_config and ws_config.mode == "worktree" and ws_config.resolved_repo()

        if use_worktree:
            repo_path = ws_config.resolved_repo()
            branch_name = _branch_name_from_key(key)
            ok = await _create_worktree(
                repo_path, ws_path, branch_name, ws_config.base_ref, hooks.timeout_ms,
            )
            if not ok:
                shutil.rmtree(ws_path, ignore_errors=True)
                raise RuntimeError(f"worktree creation failed for {issue_identifier}")
        else:
            ws_path.mkdir(parents=True, exist_ok=True)

        if hooks.after_create:
            ok = await run_hook(hooks.after_create, ws_path, hooks.timeout_ms, "after_create")
            if not ok:
                if use_worktree:
                    repo_path = ws_config.resolved_repo()
                    branch_name = _branch_name_from_key(key)
                    await _remove_worktree(repo_path, ws_path, branch_name)
                else:
                    shutil.rmtree(ws_path, ignore_errors=True)
                raise RuntimeError(f"after_create hook failed for {issue_identifier}")

    return WorkspaceResult(path=ws_path, workspace_key=key, created_now=created_now)


async def remove_workspace(
    workspace_root: Path,
    issue_identifier: str,
    hooks: HooksConfig,
    ws_config: WorkspaceConfig | None = None,
) -> None:
    """Remove a workspace directory for a terminal issue."""
    key = sanitize_key(issue_identifier)
    ws_path = workspace_root / key

    if not ws_path.exists():
        return

    if hooks.before_remove:
        await run_hook(hooks.before_remove, ws_path, hooks.timeout_ms, "before_remove")

    use_worktree = ws_config and ws_config.mode == "worktree" and ws_config.resolved_repo()

    if use_worktree:
        repo_path = ws_config.resolved_repo()
        branch_name = _branch_name_from_key(key)
        logger.info(f"Removing worktree issue={issue_identifier} path={ws_path}")
        await _remove_worktree(repo_path, ws_path, branch_name)
    else:
        logger.info(f"Removing workspace issue={issue_identifier} path={ws_path}")
        shutil.rmtree(ws_path, ignore_errors=True)
