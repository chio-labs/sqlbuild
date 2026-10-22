"""Focused entry that fails when the bundled docs reference pages are out of date."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.docs_skill._helpers.output import outdated_reference_pages
from scripts.docs_skill._helpers.recall_schema import render_recall_views, with_recall_views
from scripts.docs_skill._helpers.render import build_reference_pages
from scripts.docs_skill.constants import DEFAULT_DOCS_ROOT, DEFAULT_OUTPUT_DIR, INVESTIGATION_GUIDE


def check_docs_skill(argv: list[str] | None = None) -> int:
    """Compare freshly generated reference pages with the committed ones."""

    args: argparse.Namespace = _parse_args(argv)
    outdated: tuple[str, ...] = outdated_reference_pages(
        output_dir=args.output_dir,
        pages=build_reference_pages(docs_root=args.docs_root),
    )
    if args.investigation_guide is not None:
        guide: str = args.investigation_guide.read_text(encoding="utf-8")
        if with_recall_views(guide=guide, views=render_recall_views()) != guide:
            outdated = (*outdated, args.investigation_guide.as_posix())
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
    parser.add_argument(
        "--investigation-guide",
        type=Path,
        default=INVESTIGATION_GUIDE,
        help="guide whose Recall schema section is checked; '' skips it",
    )
    args: argparse.Namespace = parser.parse_args(argv)
    if args.investigation_guide == Path():
        args.investigation_guide = None
    return args
