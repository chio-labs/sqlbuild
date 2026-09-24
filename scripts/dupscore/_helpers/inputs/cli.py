"""Parse and validate dupscore command-line arguments."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.dupscore.constants import (
    CLONES_MODE,
    DEFAULT_CLONE_MIN_SIMILARITY,
    DEFAULT_CLONE_MIN_TOKENS,
    PAIR_MODE,
    REPORT_MODE,
    SUPPORTED_LANGUAGES,
)
from scripts.dupscore.models import CloneOptions

_CLONE_ONLY_OPTIONS: dict[str, str] = {
    "min_similarity": "--min-similarity",
    "min_tokens": "--min-tokens",
    "language": "--lang",
    "path_globs": "--path",
    "include_tests": "--include-tests",
}
_MAX_SIMILARITY: float = 1.0
_MIN_POSITIVE_COUNT: int = 1


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI arguments, exiting with a usage error for invalid combinations."""

    parser: argparse.ArgumentParser = _build_parser()
    args: argparse.Namespace = parser.parse_args(argv)
    problem: str | None = _argument_problem(args)
    if problem is not None:
        parser.error(problem)
    return args


def clone_options_from(args: argparse.Namespace) -> CloneOptions:
    """Build clone-mode options from parsed arguments and defaults."""

    return CloneOptions(
        languages=(args.language,) if args.language is not None else SUPPORTED_LANGUAGES,
        include_tests=bool(args.include_tests),
        min_tokens=args.min_tokens if args.min_tokens is not None else DEFAULT_CLONE_MIN_TOKENS,
        min_similarity=(
            args.min_similarity if args.min_similarity is not None else DEFAULT_CLONE_MIN_SIMILARITY
        ),
        path_globs=tuple(args.path_globs or ()),
        since=args.since,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="dupscore",
        description=(
            "Duplication advisory tool. 'clones' (default) reports concrete function-level "
            "clones in Python and Rust; 'report' ranks package pairs; 'pair' drills into one."
        ),
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=[CLONES_MODE, REPORT_MODE, PAIR_MODE],
        default=CLONES_MODE,
    )
    parser.add_argument("packages", nargs="*", default=[])
    parser.add_argument("--top", type=int, default=None, help="Number of entries to print.")
    parser.add_argument("--domain", type=str, default=None, help="report: package prefix.")
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="clones: only clusters touching lines changed since REV; report: delta vs REV.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository to analyze.")
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=None,
        help=f"clones: minimum token similarity (default {DEFAULT_CLONE_MIN_SIMILARITY}).",
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=None,
        help=f"clones: minimum normalised tokens per unit (default {DEFAULT_CLONE_MIN_TOKENS}).",
    )
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default=None,
        dest="language",
        help="clones: analyze one language only.",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=None,
        dest="path_globs",
        help="clones: only clusters with a member matching this glob (repeatable).",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        default=None,
        help="clones: also analyze Python tests/ and Rust test modules.",
    )
    return parser


def _argument_problem(args: argparse.Namespace) -> str | None:
    if args.mode != CLONES_MODE:
        misused: list[str] = [
            flag for attribute, flag in _CLONE_ONLY_OPTIONS.items() if getattr(args, attribute)
        ]
        return f"{', '.join(misused)} only apply to the {CLONES_MODE} mode" if misused else None
    if args.packages:
        return f"the {CLONES_MODE} mode takes no positional package names"
    if args.domain is not None:
        return f"--domain only applies to the {REPORT_MODE} mode"
    if args.top is not None and args.top < _MIN_POSITIVE_COUNT:
        return "--top must be at least 1"
    if args.min_tokens is not None and args.min_tokens < _MIN_POSITIVE_COUNT:
        return "--min-tokens must be at least 1"
    if args.min_similarity is not None and not 0.0 < args.min_similarity <= _MAX_SIMILARITY:
        return "--min-similarity must be in (0, 1]"
    return None
