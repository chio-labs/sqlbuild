"""ANSI color helpers for terminal output."""

from __future__ import annotations

import os
import sys

_RESET: str = "\033[0m"
_BOLD: str = "\033[1m"
_DIM: str = "\033[2m"
_RED: str = "\033[31m"
_GREEN: str = "\033[32m"
_YELLOW: str = "\033[33m"
_BLUE: str = "\033[34m"


def blue(text: str) -> str:
    """Blue text for structural/informational elements."""

    return f"{_BLUE}{text}{_RESET}"


def green(text: str) -> str:
    """Green text for success/added elements."""

    return f"{_GREEN}{text}{_RESET}"


def yellow(text: str) -> str:
    """Yellow text for warnings/changed elements."""

    return f"{_YELLOW}{text}{_RESET}"


def red(text: str) -> str:
    """Red text for errors/removed elements."""

    return f"{_RED}{text}{_RESET}"


def red_bold(text: str) -> str:
    """Red bold text for error prefixes."""

    return f"{_RED}{_BOLD}{text}{_RESET}"


def red_dim(text: str) -> str:
    """Muted red text for softer error labels."""

    return f"{_RED}{_DIM}{text}{_RESET}"


def bold(text: str) -> str:
    """Bold text for section headers."""

    return f"{_BOLD}{text}{_RESET}"


def blue_bold(text: str) -> str:
    """Blue bold text for model names."""

    return f"{_BLUE}{_BOLD}{text}{_RESET}"


def green_bold(text: str) -> str:
    """Green bold text for successful section headers."""

    return f"{_GREEN}{_BOLD}{text}{_RESET}"


def yellow_bold(text: str) -> str:
    """Yellow bold text for warning section headers."""

    return f"{_YELLOW}{_BOLD}{text}{_RESET}"


def dim(text: str) -> str:
    """Dim text for skipped/inactive elements."""

    return f"{_DIM}{text}{_RESET}"


def blue_dim(text: str) -> str:
    """Muted blue text for informational lifecycle messages."""

    return f"{_BLUE}{_DIM}{text}{_RESET}"


def supports_color() -> bool:
    """Check if the terminal supports color output."""

    if os.environ.get("NO_COLOR") is not None:
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


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
