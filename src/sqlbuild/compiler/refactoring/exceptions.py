"""Expected refactoring errors."""

from __future__ import annotations


class RefactorValueError(ValueError):
    """An unhandled value failure the Python planner also leaves to the caller."""


class RefactorIOError(OSError):
    """A file read or write failure the Python planner also leaves to the caller."""
