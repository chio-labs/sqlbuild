"""Structured models for SQLBuild docs skill generation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MdxPage:
    """Content extracted from one MDX documentation page."""

    title: str
    description: str
    body: str
