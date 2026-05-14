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
