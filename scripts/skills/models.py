"""Skill generation models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleReference:
    """One generated structure convention rule reference."""

    code: str
    message: str
