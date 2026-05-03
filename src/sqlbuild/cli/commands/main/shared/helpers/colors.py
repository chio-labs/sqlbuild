"""ANSI color helpers for CLI output."""

from __future__ import annotations

_RESET: str = "\033[0m"
_BOLD: str = "\033[1m"
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


def bold(text: str) -> str:
    """Bold text for section headers."""

    return f"{_BOLD}{text}{_RESET}"


def blue_bold(text: str) -> str:
    """Blue bold text for model names."""

    return f"{_BLUE}{_BOLD}{text}{_RESET}"


def yellow_bold(text: str) -> str:
    """Yellow bold text for warning section headers."""

    return f"{_YELLOW}{_BOLD}{text}{_RESET}"
