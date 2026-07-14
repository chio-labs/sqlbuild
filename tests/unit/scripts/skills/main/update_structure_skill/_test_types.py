from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StructureSkillGenerationTestCase:
    description: str
    source_relative_path: Path
    source_contents: str
    expected_fragments: tuple[str, ...]
