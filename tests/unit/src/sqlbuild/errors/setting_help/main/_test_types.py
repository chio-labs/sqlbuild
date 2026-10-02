from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SettingHelpTestCase:
    description: str
    rendered: str
    expected_text: str


@dataclass(frozen=True)
class SettingSnippetTestCase:
    description: str
    help_text: str
    expected_section: str
    expected_key: str
    expected_value: object


@dataclass(frozen=True)
class SettingCatalogueTestCase:
    description: str
    repository_root: Path
    expected_findings: tuple[str, ...]
