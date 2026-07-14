"""Focused entry for SQLBuild structure skill generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.skills._helpers.structure_generation import build_skill_markdown
from scripts.skills.constants import (
    DEFAULT_STRUCTURE_RULES_PATH,
    DEFAULT_STRUCTURE_SKILL_OUTPUT_PATH,
)


def update_structure_skill(argv: list[str] | None = None) -> int:
    """Generate and write the SQLBuild structure skill."""

    args: argparse.Namespace = _parse_args(argv)
    skill_markdown: str = build_skill_markdown(
        repo_root=args.repo_root,
        source_path=args.source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(skill_markdown, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Generate the SQLBuild structure skill."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=DEFAULT_STRUCTURE_RULES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_STRUCTURE_SKILL_OUTPUT_PATH)
    return parser.parse_args(argv)
