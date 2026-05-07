"""Create a local SQLBuild playground project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.playground.copy import create_playground_project


def run_playground(project_dir: Path | None, target_path: str) -> int:
    """Create a self-contained waffle shop playground project."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    target_dir: Path = Path(target_path)
    if not target_dir.is_absolute():
        target_dir = base_dir / target_dir

    create_playground_project(target_dir=target_dir)
    display_path: str = str(target_path)
    print("SQLBuild playground created")
    print()
    print(f"  Project: {display_path}")
    print("  Adapter: DuckDB")
    print("  Example: waffle shop")
    print()
    print("Try:")
    print(f"  cd {display_path}")
    print("  sqb compile")
    print("  sqb build")
    print("  sqb test")
    print("  sqb audit")
    return 0
