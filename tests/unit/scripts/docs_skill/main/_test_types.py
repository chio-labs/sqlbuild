from dataclasses import dataclass


@dataclass(frozen=True)
class DocsSkillCheckTestCase:
    description: str
    output_edits: dict[str, str]
    expected_exit_code: int
    expected_outdated: tuple[str, ...]
