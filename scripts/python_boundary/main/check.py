"""Python boundary ratchet command entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.python_boundary._helpers.lines import count_lines, tracked_python_files
from scripts.python_boundary._helpers.native_errors import find_native_error_handlers
from scripts.python_boundary._helpers.policy import get_policy_errors, read_boundary_policy
from scripts.python_boundary.constants import POLICY_FILE, SOURCE_ROOT
from scripts.python_boundary.models import BoundaryPolicy, NativeErrorHandler


def run_python_boundary_check(argv: list[str] | None = None) -> int:
    """Fail when movable Python changes without the policy or swallows native failures."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments: argparse.Namespace = parser.parse_args(argv)
    root: Path = arguments.root
    policy: BoundaryPolicy = read_boundary_policy(root / POLICY_FILE)
    errors: list[str] = list(get_policy_errors(root=root, policy=policy))
    tracked: tuple[Path, ...] = tracked_python_files(root=root, stays=policy.stays)
    remaining: int = count_lines(tracked)
    if remaining > policy.remaining_lines:
        errors.append(
            f"Movable Python grew to {remaining} lines (policy: {policy.remaining_lines}). "
            "Move the new code to Rust, or justify it in python-boundary.toml."
        )
    elif remaining < policy.remaining_lines:
        errors.append(
            f"Movable Python shrank to {remaining} lines; "
            f"set remaining_lines = {remaining} in {POLICY_FILE}."
        )
    reviewed: frozenset[str] = frozenset(
        handler.location for handler in policy.handled_native_errors
    )
    found: tuple[NativeErrorHandler, ...] = find_native_error_handlers(
        source=root / SOURCE_ROOT, paths=tracked
    )
    for handler in found:
        if handler.location not in reviewed:
            errors.append(
                f"{SOURCE_ROOT}/{handler.location.split('::')[0]}:{handler.line} swallows a "
                "native failure; re-raise it, or list the function in handled_native_errors "
                "with a reason. Native failures must not fall back to Python."
            )
    present: frozenset[str] = frozenset(handler.location for handler in found)
    errors.extend(
        f"handled_native_errors entry {location!r} no longer matches any handler; remove it."
        for location in sorted(reviewed - present)
    )
    if errors:
        print("Python boundary check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Python boundary is valid: {remaining} movable Python lines remain.")
    return 0
