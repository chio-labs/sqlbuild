"""Pull request metadata command entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.pr_metadata._helpers.inputs import get_current_branch, load_event_metadata
from scripts.pr_metadata._helpers.validation import get_pr_metadata_errors


def run_pr_metadata_validation(argv: list[str] | None = None) -> int:
    """Validate metadata supplied directly or through a GitHub event payload."""
    parser: argparse.ArgumentParser = _build_parser()
    arguments: argparse.Namespace = parser.parse_args(argv)
    branch: str
    title: str
    body: str
    if arguments.metadata_file is not None:
        branch, title, body = load_event_metadata(arguments.metadata_file)
    else:
        if arguments.title is None or arguments.body_file is None:
            parser.error("--title and --body-file are required without --metadata-file")
        branch = arguments.branch or get_current_branch()
        title = arguments.title
        body = arguments.body_file.read_text(encoding="utf-8")

    errors: tuple[str, ...] = get_pr_metadata_errors(branch=branch, title=title, body=body)
    if errors:
        print(f"Invalid pull request metadata for {branch}:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Pull request metadata is valid for {branch}.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-file", type=Path)
    parser.add_argument("--branch")
    parser.add_argument("--title")
    parser.add_argument("--body-file", type=Path)
    return parser
