from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillsCliTestCase:
    description: str
    argv: list[str]
    expected_exit_code: int
    expected_files: tuple[Path, ...]
    unexpected_files: tuple[Path, ...] = ()
    expected_content_fragment: str = "# SQLBuild Skill"


@dataclass(frozen=True)
class SkillsCliOverwriteTestCase:
    description: str
    argv: list[str]
    existing_file: Path
    existing_content: str
    expected_exit_code: int
    expected_content_fragment: str
