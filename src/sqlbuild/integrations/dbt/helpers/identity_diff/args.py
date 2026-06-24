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
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--full-diff", action="store_true", default=False)
    parser.add_argument("--json", dest="json_output", action="store_true", default=False)
    parsed: argparse.Namespace = parser.parse_args(args)
    return DbtIdentityDiffArgs(
        select=tuple(parsed.select),
        exclude=tuple(parsed.exclude),
        against=parsed.against,
        quiet=parsed.quiet,
        depth=parsed.depth,
        json_output=parsed.json_output,
        full_diff=parsed.full_diff,
    )
