from dataclasses import dataclass


@dataclass(frozen=True)
class ParseAuditInstanceTestCase:
    description: str
    raw_audit: object
    expected_definition_name: str
    expected_always_run: bool
    expected_argument_keys: tuple[str, ...]


@dataclass(frozen=True)
class ParseAuditInstanceErrorTestCase:
    description: str
    raw_audit: object
    expected_error_fragment: str
