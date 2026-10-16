from dataclasses import dataclass, field


@dataclass(frozen=True)
class FactDigestEditTestCase:
    description: str
    key: tuple[str, ...]
    edited_files: dict[str, str]
    expected_digest_changes: bool = True
    base_files: dict[str, str] = field(default_factory=dict)
