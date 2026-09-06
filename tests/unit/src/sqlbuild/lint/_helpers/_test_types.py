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
class InvalidNativeSqlResponseTestCase:
    """Test case for rejecting malformed native SQL lint responses."""

    description: str
    response: str
    expected_message: str


@dataclass(frozen=True)
class NativeSqlReuseTestCase:
    """Identity for native SQL reuse behavior."""

    description: str
    expected_call_count: int


@dataclass(frozen=True)
class NativeParseIsolationTestCase:
    """Native parser fault that must not stop later bodies."""

    description: str
    error_message: str
    expected_position: tuple[int, int]


@dataclass(frozen=True)
class ReservedCteLintTestCase:
    """Test case for SQLBuild harness CTE filtering."""

    description: str
    sql: str
    expected_violation_count: int


@dataclass(frozen=True)
class GeneratedRangeFallbackTestCase:
    """Test case for a diagnostic that crosses generated SQL."""

    description: str
    authored: str
    expanded: str
    diagnostic_start: int
    diagnostic_end: int
    expected_position: tuple[int, int]


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
    """Test case for restoring sentinels after native formatting."""

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
