from dataclasses import dataclass


@dataclass(frozen=True)
class FactDigestEditTestCase:
    description: str
    key: tuple[str, ...]
    edited_files: dict[str, str]
    expected_digest_changes: bool = True
