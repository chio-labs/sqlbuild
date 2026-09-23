"""Focused entry for SQLBuild docs reference generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.docs_skill._helpers.clone import clone_docs_repo
from scripts.docs_skill._helpers.output import write_reference_pages
from scripts.docs_skill._helpers.render import build_reference_pages
from scripts.docs_skill.constants import DEFAULT_CLONE_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_REPO_URL


def generate_docs_skill(argv: list[str] | None = None) -> int:
    """Generate the bundled documentation reference pages for the SQLBuild skill."""

    args: argparse.Namespace = _parse_args(argv)
    docs_root: Path = args.docs_root or clone_docs_repo(
        repo_url=args.repo_url,
        clone_dir=args.clone_dir,
    )
    write_reference_pages(
        output_dir=args.output_dir,
        pages=build_reference_pages(docs_root=docs_root),
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Clone sqlbuild-docs and convert each MDX page into a bundled skill reference page."
        )
    )
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--clone-dir", type=Path, default=DEFAULT_CLONE_DIR)
    parser.add_argument("--docs-root", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)
