"""Test case dataclasses for lint helper unit tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanHeadersTestCase:
    """Test case for scan_headers."""

    description: str
    contents: str
    expected_kinds: tuple[str, ...]


@dataclass(frozen=True)
class HeaderSpanTextTestCase:
    """Test case asserting one header span covers its full region."""

    description: str
    contents: str
    expected_span_text: str


@dataclass(frozen=True)
class SqlBodyRangesTestCase:
    """Test case for sql_body_ranges."""

    description: str
    contents: str
    expected_fragments: tuple[str, ...]
    excluded_fragments: tuple[str, ...]


@dataclass(frozen=True)
class LintNativeTestCase:
    """Test case for native header lint rules."""

    description: str
    contents: str
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class FormatNativeTestCase:
    """Test case for native header formatting."""

    description: str
    contents: str
    expected_contents: str
    expected_fault_codes: tuple[str, ...]


@dataclass(frozen=True)
class SqruffEngineLintTestCase:
    """Test case for the sqruff lint wrapper with a canned engine response."""

    description: str
    contents: str
    stdout: str
    expected_lines: tuple[int, ...]
    expected_columns: tuple[int, ...]
    expected_codes: tuple[str, ...]
    bodies_empty: bool = False
    expected_engine_calls: int = 1


@dataclass(frozen=True)
class SqruffEngineFixTestCase:
    """Test case for the sqruff fix wrapper with a canned engine response."""

    description: str
    contents: str
    fixed_body: str
    expected_contents: str


@dataclass(frozen=True)
class SqruffNoBodiesTestCase:
    """Test case for the sqruff wrapper invoked with no SQL bodies."""

    description: str
    expected_violation_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class NeutralizeInterpolationTestCase:
    """Test case for interpolation neutralization."""

    description: str
    body: str
    expected_neutralized: str
    expected_original_texts: tuple[str, ...]


@dataclass(frozen=True)
class MapOffsetTestCase:
    """Test case for neutralized-to-original offset mapping."""

    description: str
    body: str
    neutralized_offset: int
    expected_original_offset: int


@dataclass(frozen=True)
class RestoreInterpolationTestCase:
    """Test case for restoring sentinels after sqruff fixes."""

    description: str
    body: str
    fixed_neutralized: str
    expected_restored: str


@dataclass(frozen=True)
class RestoreFailureTestCase:
    """Test case for sentinel restoration that must fail loudly."""

    description: str
    body: str
    fixed_neutralized: str
    expected_message_fragment: str
