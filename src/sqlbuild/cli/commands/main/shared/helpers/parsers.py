"""Shared CLI parser helpers."""

from __future__ import annotations

import argparse


def add_cursor_override_args(parser: argparse.ArgumentParser) -> None:
    """Add typed cursor override flags to a subparser."""

    parser.add_argument("--start-cursor-ts", default=None)
    parser.add_argument("--end-cursor-ts", default=None)
    parser.add_argument("--start-cursor-int", default=None)
    parser.add_argument("--end-cursor-int", default=None)


def add_execution_args(parser: argparse.ArgumentParser) -> None:
    """Add execution control flags shared by build and run commands."""

    parser.add_argument("--fail-fast", action="store_true", default=False)
    parser.add_argument("--full-refresh", action="store_true", default=False)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--verbose", "-v", action="store_true", default=False)


def add_select_args(parser: argparse.ArgumentParser) -> None:
    """Add --select and --exclude flags for scope selection."""

    parser.add_argument("--select", "-s", nargs="+", action="extend", default=[])
    parser.add_argument("--exclude", nargs="+", action="extend", default=[])
