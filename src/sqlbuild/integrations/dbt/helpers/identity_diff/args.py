"""dbt identity-diff argument parsing helpers."""

from __future__ import annotations

import argparse

from sqlbuild.integrations.dbt.models import DbtIdentityDiffArgs


def parse_dbt_identity_diff_args(*, args: tuple[str, ...]) -> DbtIdentityDiffArgs:
    """Parse `sqb dbt identity-diff` arguments."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb dbt identity-diff")
    parser.add_argument("--select", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--against", default=None)
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--show-inherited", action="store_true", default=False)
    parser.add_argument("--paths", dest="show_paths", action="store_true", default=False)
    parser.add_argument("--strict-reuse", dest="strict_reuse", action="store_true")
    parser.add_argument("--no-strict-reuse", dest="strict_reuse", action="store_false")
    parser.set_defaults(strict_reuse=None)
    parser.add_argument("--max-diff-lines", type=int, default=2000)
    parser.add_argument("--max-diff-bytes", type=int, default=200_000)
    parser.add_argument("--json", dest="json_output", action="store_true", default=False)
    parsed: argparse.Namespace = parser.parse_args(args)
    return DbtIdentityDiffArgs(
        select=tuple(parsed.select),
        exclude=tuple(parsed.exclude),
        against=parsed.against,
        quiet=parsed.quiet,
        json_output=parsed.json_output,
        show_inherited=parsed.show_inherited,
        show_paths=parsed.show_paths,
        max_diff_lines=parsed.max_diff_lines,
        max_diff_bytes=parsed.max_diff_bytes,
        strict_reuse=parsed.strict_reuse,
    )
