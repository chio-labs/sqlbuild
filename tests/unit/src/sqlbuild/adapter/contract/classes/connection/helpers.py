"""Callbacks for connection contract tests."""

from __future__ import annotations


def interrupt() -> None:
    """Raise as a crash inside a transaction would."""

    raise RuntimeError("simulated interruption")


def carry_on() -> None:
    """Do nothing."""
