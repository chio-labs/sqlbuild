"""Python boundary policy models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StayEntry:
    """A module or package that stays Python, the rule that keeps it, and the evidence."""

    path: str
    rule: object
    note: str
    unknown_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewedNativeHandler:
    """A reviewed function that handles a native failure without re-raising it."""

    location: str
    note: str


@dataclass(frozen=True)
class BoundaryPolicy:
    """The committed remaining-line count, the Python that stays, and reviewed handlers."""

    remaining_lines: int
    stays: tuple[StayEntry, ...]
    handled_native_errors: tuple[ReviewedNativeHandler, ...]


@dataclass(frozen=True)
class NativeErrorHandler:
    """A function that calls the native module inside `try` and swallows the failure."""

    location: str
    line: int
