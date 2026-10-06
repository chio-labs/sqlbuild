from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDigestTestCase:
    description: str
    edited_source_names: tuple[str, ...]
    edited_contents: str
    expected_equal: bool


@dataclass(frozen=True)
class ModelFactDigestTestCase:
    description: str
    fact: str
    expected_host_digest_match: bool
