"""Shared CLI parser helpers."""

from __future__ import annotations

import argparse


def add_cursor_override_args(parser: argparse.ArgumentParser) -> None:
    """Add typed cursor override flags to a subparser."""

    parser.add_argument("--start-cursor-ts", default=None)
    parser.add_argument("--end-cursor-ts", default=None)
    parser.add_argument("--start-cursor-int", default=None)
    parser.add_argument("--end-cursor-int", default=None)
