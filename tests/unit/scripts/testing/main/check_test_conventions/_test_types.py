from dataclasses import dataclass


@dataclass(frozen=True)
class CheckPathsTestCase:
    description: str
    repo_files: dict[str, str]
    expected_violation_codes: tuple[str, ...]
    expected_message_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckCliMainTestCase:
    description: str
    repo_files: dict[str, str]
    expected_exit_code: int
