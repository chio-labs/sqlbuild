"""Structured models for SQLBuild docs reference generation."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MdxPage:
    """Content extracted from one MDX documentation page."""

    title: str
    description: str
    body: str


@dataclass(frozen=True, slots=True)
class NavigationGroup:
    """One navigation group label and its pages in documentation order."""

    label: str
    page_paths: tuple[Path, ...]
