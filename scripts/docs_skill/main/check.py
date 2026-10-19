"""Focused entry that fails when the bundled docs reference pages are out of date."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.docs_skill._helpers.output import outdated_reference_pages
from scripts.docs_skill._helpers.render import build_reference_pages
from scripts.docs_skill.constants import DEFAULT_DOCS_ROOT, DEFAULT_OUTPUT_DIR


def check_docs_skill(argv: list[str] | None = None) -> int:
    """Compare freshly generated reference pages with the committed ones."""

    args: argparse.Namespace = _parse_args(argv)
    outdated: tuple[str, ...] = outdated_reference_pages(
        output_dir=args.output_dir,
        pages=build_reference_pages(docs_root=args.docs_root),
    )
    if not outdated:
        print(f"Docs skill reference pages in {args.output_dir} are up to date")
        return 0
    print(
        f"{len(outdated)} docs skill reference page(s) in {args.output_dir} are out of date "
        "with the website docs. Run `make skills` and commit the result:",
        file=sys.stderr,
    )
    for relative_path in outdated:
        print(f"  {relative_path}", file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Fail when bundled SQLBuild skill reference pages differ from the website docs."
    )
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)
