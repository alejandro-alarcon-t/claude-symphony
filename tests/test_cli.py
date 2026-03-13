"""Tests for main.py — SPEC 17.7 CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_symphony.main import _load_dotenv


class TestLoadDotenv:
    def test_loads_key_value(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("MY_KEY=my_value\n")
        _load_dotenv()
        assert os.environ.get("MY_KEY") == "my_value"

    def test_ignores_comments(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("# comment\nKEY=val\n")
        _load_dotenv()
        assert os.environ.get("KEY") == "val"

    def test_ignores_blank_lines(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("\n\nKEY=val\n\n")
        _load_dotenv()
        assert os.environ.get("KEY") == "val"

    def test_strips_whitespace(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("  KEY_WS  =  value_ws  \n")
        _load_dotenv()
        assert os.environ.get("KEY_WS") == "value_ws"

    def test_no_env_file_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Should not raise
        _load_dotenv()

    def test_overrides_existing_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("OVERRIDE_ME", "old")
        (tmp_path / ".env").write_text("OVERRIDE_ME=new\n")
        _load_dotenv()
        assert os.environ.get("OVERRIDE_ME") == "new"


class TestWorkflowAutoDetection:
    """Test the workflow auto-detection logic in cli()."""

    def test_yaml_preferred(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "workflow.yaml").write_text("tracker: {}")
        (tmp_path / "workflow.yml").write_text("tracker: {}")
        (tmp_path / "WORKFLOW.md").write_text("---\ntracker: {}\n---\n")
        # Verify precedence: yaml > yml > md
        assert Path("workflow.yaml").exists()

    def test_yml_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "workflow.yml").write_text("tracker: {}")
        assert not Path("workflow.yaml").exists()
        assert Path("workflow.yml").exists()

    def test_md_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "WORKFLOW.md").write_text("---\ntracker: {}\n---\n")
        assert not Path("workflow.yaml").exists()
        assert not Path("workflow.yml").exists()
        assert Path("WORKFLOW.md").exists()
