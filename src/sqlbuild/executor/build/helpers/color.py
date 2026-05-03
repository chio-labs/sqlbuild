"""Terminal color support for build output."""

from __future__ import annotations

import os
import sys


def supports_color() -> bool:
    """Check if the terminal supports color output."""

    if os.environ.get("NO_COLOR") is not None:
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


def green(text: str) -> str:
    return f"\033[32m{text}\033[0m"


def yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m"


def red(text: str) -> str:
    return f"\033[31m{text}\033[0m"


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


def blue_dim(text: str) -> str:
    return f"\033[34m\033[2m{text}\033[0m"


def colorize_status(status: str, *, use_color: bool) -> str:
    """Apply color to a status word based on its value."""

    if not use_color:
        return status
    if status in ("OK", "PASS"):
        return green(status)
    if status == "WARN":
        return yellow(status)
    if status == "FAIL":
        return red(status)
    if status == "SKIP":
        return dim(status)
    return status


def colorize_completion(message: str, *, use_color: bool) -> str:
    """Apply color to the completion status message."""

    if not use_color:
        return message
    if "errors" in message:
        return red(message)
    if "warnings" in message:
        return yellow(message)
    return green(message)
