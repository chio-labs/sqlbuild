"""Shared fixtures for unit tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def write_repo_files() -> Callable[[Path, dict[str, str]], None]:
    """Write a dictionary of relative-path to content pairs into a directory."""

    def _write(repo_root: Path, repo_files: dict[str, str]) -> None:
        for relative_path, content in repo_files.items():
            file_path: Path = repo_root / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

    return _write
