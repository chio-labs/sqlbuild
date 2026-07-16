"""Focused entry for SQLBuild docs skill generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.docs_skill._helpers.clone import clone_docs_repo
from scripts.docs_skill._helpers.output import write_skill_markdown
from scripts.docs_skill._helpers.render import build_skill_markdown
from scripts.docs_skill.constants import DEFAULT_CLONE_DIR, DEFAULT_OUTPUT_PATH, DEFAULT_REPO_URL


def generate_docs_skill(argv: list[str] | None = None) -> int:
    """Generate and write the SQLBuild documentation skill."""

    args: argparse.Namespace = _parse_args(argv)
    docs_root: Path = args.docs_root or clone_docs_repo(
        repo_url=args.repo_url,
        clone_dir=args.clone_dir,
    )
    skill_markdown: str = build_skill_markdown(
        docs_root=docs_root,
        include_introduction=not args.exclude_introduction,
    )
    write_skill_markdown(output_path=args.output, contents=skill_markdown)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Clone sqlbuild-docs and convert all MDX pages into a single SKILL.md."
    )
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--clone-dir", type=Path, default=DEFAULT_CLONE_DIR)
    parser.add_argument("--docs-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--exclude-introduction", action="store_true")
    return parser.parse_args(argv)
