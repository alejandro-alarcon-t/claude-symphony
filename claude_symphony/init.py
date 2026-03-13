"""claude-symphony init — scaffold a workflow.yaml for a target repo."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

console = Console()

# File-extension → language name
_LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".vue": "Vue",
    ".svelte": "Svelte",
}


def _detect_languages(repo: Path) -> list[str]:
    """Detect primary languages by scanning file extensions."""
    counts: dict[str, int] = {}
    for root, dirs, files in os.walk(repo):
        # Skip hidden dirs, node_modules, venv, etc.
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".")
            and d not in ("node_modules", "__pycache__", ".venv", "venv",
                          "vendor", "dist", "build", "target")
        ]
        for f in files:
            ext = Path(f).suffix.lower()
            lang = _LANG_MAP.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    # Return languages sorted by frequency
    return [
        lang for lang, _ in sorted(counts.items(), key=lambda x: -x[1])
    ]


def _detect_git_remote(repo: Path) -> str:
    """Get the git remote URL if available."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _detect_package_manager(repo: Path) -> str:
    """Detect the primary package manager."""
    if (repo / "uv.lock").exists() or (repo / "pyproject.toml").exists():
        return "uv"
    if (repo / "Pipfile").exists():
        return "pipenv"
    if (repo / "requirements.txt").exists():
        return "pip"
    if (repo / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (repo / "yarn.lock").exists():
        return "yarn"
    has_lock = (repo / "package-lock.json").exists()
    if has_lock or (repo / "package.json").exists():
        return "npm"
    if (repo / "go.mod").exists():
        return "go"
    if (repo / "Cargo.toml").exists():
        return "cargo"
    if (repo / "Gemfile").exists():
        return "bundler"
    return ""


def _build_clone_hook(remote: str, pkg_mgr: str) -> str:
    """Build the after_create hook for clone mode."""
    lines = []
    if remote:
        lines.append(f"git clone --depth 1 {remote} .")
    else:
        lines.append("# git clone --depth 1 <your-repo-url> .")

    install_cmds = {
        "uv": "uv sync",
        "pip": "pip install -r requirements.txt",
        "pipenv": "pipenv install",
        "npm": "npm install",
        "pnpm": "pnpm install",
        "yarn": "yarn install",
        "go": "go mod download",
        "cargo": "cargo fetch",
        "bundler": "bundle install",
    }
    if pkg_mgr in install_cmds:
        lines.append(install_cmds[pkg_mgr])

    return "\n".join(lines)


def _generate_workflow(
    repo: Path,
    remote: str,
    languages: list[str],
    pkg_mgr: str,
    use_worktree: bool,
) -> str:
    """Generate the workflow.yaml content."""
    lang_str = ", ".join(languages[:3]) if languages else "unknown"

    # Tracker section
    tracker = (
        'tracker:\n'
        '  kind: linear\n'
        '  # Use ONE of project_slug or team_key:\n'
        '  project_slug: ""     # hex slugId from Linear project URL\n'
        '  # team_key: ""       # or team key like "ENG"\n'
        '  # api_key: $LINEAR_API_KEY\n'
    )

    # Workspace section
    if use_worktree:
        workspace = (
            'workspace:\n'
            f'  root: {repo / ".symphony-workspaces"}\n'
            '  mode: worktree\n'
            f'  repo: {repo}\n'
            '  base_ref: origin/main\n'
        )
        hooks = (
            'hooks:\n'
            '  timeout_ms: 120000\n'
        )
    else:
        workspace = (
            'workspace:\n'
            f'  root: {repo / ".symphony-workspaces"}\n'
        )
        hooks = (
            'hooks:\n'
            '  after_create: |\n'
        )
        for line in _build_clone_hook(remote, pkg_mgr).splitlines():
            hooks += f'    {line}\n'
        hooks += (
            '  before_run: |\n'
            '    git fetch origin main\n'
            '    git rebase origin/main 2>/dev/null || git rebase --abort\n'
            '  timeout_ms: 120000\n'
        )

    # Build the full YAML
    yaml = f"""\
# Claude Symphony workflow for: {repo.name}
# Detected: {lang_str}
# Docs: https://github.com/alejandro-alarcon-t/claude-symphony

{tracker}
linear_states:
  active: "In Progress"
  review: "Human Review"
  gate_approved: "Gate Approved"
  rework: "Rework"
  terminal:
    - Done
    - Closed
    - Cancelled

polling:
  interval_ms: 15000

{workspace}
{hooks}
claude:
  permission_mode: auto
  model: claude-sonnet-4-6
  max_turns: 20
  turn_timeout_ms: 3600000
  stall_timeout_ms: 300000

agent:
  max_concurrent_agents: 3
  max_retry_backoff_ms: 300000

prompts:
  global_prompt: prompts/global.md

states:
  implement:
    type: agent
    prompt: prompts/implement.md
    linear_state: active
    max_turns: 30
    session: inherit
    transitions:
      complete: review

  review:
    type: gate
    linear_state: review
    rework_to: implement
    max_rework: 5
    transitions:
      approve: done

  done:
    type: terminal
    linear_state: terminal
"""
    return yaml


_GLOBAL_PROMPT = """\
You are an autonomous coding agent working on this repository.

## Rules
- Read and understand existing code before making changes
- Follow existing code style and conventions
- Run tests before declaring work complete
- Create a feature branch and open a PR when implementation is done
- Keep changes focused on the issue at hand

## Repository
{%- if issue_branch %}
Branch: {{ issue_branch }}
{%- endif %}
"""

_IMPLEMENT_PROMPT = """\
## Task

Implement the changes described in this issue.

### Issue: {{ issue_identifier }} — {{ issue_title }}

{{ issue_description }}

## Steps

1. Understand the requirements from the issue description
2. Read relevant existing code to understand the codebase
3. Implement the changes
4. Write or update tests
5. Run the test suite and fix any failures
6. Create a branch named `{{ issue_branch or issue_identifier }}`
7. Commit your changes with a descriptive message
8. Push the branch and open a PR

When finished, ensure all tests pass and the code is ready for review.
"""


def run_init(target: str | None = None):
    """Run the init command interactively."""
    repo = Path(target or ".").resolve()

    if not repo.is_dir():
        console.print(f"[red]Not a directory: {repo}[/red]")
        return

    console.print(
        f"[bold]Claude Symphony init[/bold] — {repo.name}\n"
    )

    # Check if workflow.yaml already exists
    wf_path = repo / "workflow.yaml"
    if wf_path.exists():
        if not Confirm.ask(
            "[yellow]workflow.yaml already exists. Overwrite?[/yellow]",
            default=False,
        ):
            console.print("[dim]Aborted.[/dim]")
            return

    # Detect repo info
    remote = _detect_git_remote(repo)
    languages = _detect_languages(repo)
    pkg_mgr = _detect_package_manager(repo)

    console.print(f"  Remote:    {remote or '[dim]none[/dim]'}")
    lang_display = ', '.join(languages[:5]) or '[dim]none detected[/dim]'
    console.print(f"  Languages: {lang_display}")
    console.print(f"  Packages:  {pkg_mgr or '[dim]none detected[/dim]'}")
    console.print()

    # Ask about workspace mode
    is_git = (repo / ".git").exists()
    use_worktree = False
    if is_git:
        use_worktree = Confirm.ask(
            "Use git worktree mode? (recommended for git repos)",
            default=True,
        )

    # Generate
    yaml_content = _generate_workflow(
        repo, remote, languages, pkg_mgr, use_worktree,
    )

    # Write workflow.yaml
    wf_path.write_text(yaml_content)
    console.print(f"[green]Created[/green] {wf_path}")

    # Create prompts directory and example files
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    global_path = prompts_dir / "global.md"
    if not global_path.exists():
        global_path.write_text(_GLOBAL_PROMPT)
        console.print(f"[green]Created[/green] {global_path}")

    impl_path = prompts_dir / "implement.md"
    if not impl_path.exists():
        impl_path.write_text(_IMPLEMENT_PROMPT)
        console.print(f"[green]Created[/green] {impl_path}")

    console.print(
        "\n[bold]Next steps:[/bold]\n"
        "  1. Set your Linear API key:  "
        "[cyan]export LINEAR_API_KEY=lin_api_...[/cyan]\n"
        "  2. Edit [cyan]workflow.yaml[/cyan] — set "
        "[cyan]project_slug[/cyan] or [cyan]team_key[/cyan]\n"
        "  3. Customize prompts in [cyan]prompts/[/cyan]\n"
        "  4. Run:  [cyan]claude-symphony[/cyan]\n"
    )
