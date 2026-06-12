from __future__ import annotations

from pathlib import Path


def write_structure_rules_file(*, repo_root: Path, relative_path: Path, contents: str) -> Path:
    source_path: Path = repo_root / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(contents, encoding="utf-8")
    return source_path
