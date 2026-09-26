"""Focused entry for SQLBuild docs reference generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.docs_skill._helpers.output import write_reference_pages
from scripts.docs_skill._helpers.render import build_reference_pages
from scripts.docs_skill.constants import DEFAULT_DOCS_ROOT, DEFAULT_OUTPUT_DIR


def generate_docs_skill(argv: list[str] | None = None) -> int:
    """Generate the bundled documentation reference pages for the SQLBuild skill."""

    args: argparse.Namespace = _parse_args(argv)
    write_reference_pages(
        output_dir=args.output_dir,
        pages=build_reference_pages(docs_root=args.docs_root),
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Convert local SQLBuild website documentation into bundled skill reference pages."
        )
    )
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)
