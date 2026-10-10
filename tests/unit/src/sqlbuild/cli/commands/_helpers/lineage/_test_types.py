from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineageSelectionTestCase:
    description: str
    target: str
    direction: str
    depth: int | None
    expected_node_ids: tuple[str, ...]
    expected_edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class ColumnLineageSelectionTestCase:
    description: str
    target: str
    direction: str
    depth: int | None
    expected_resource_name: str
    expected_column_name: str
    expected_trace_ids: tuple[str, ...]
    expected_analyzed_model_names: tuple[str, ...]
    expected_truncated: bool


@dataclass(frozen=True)
class LineageSelectorDepthErrorTestCase:
    description: str
    select: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class LineageOutputTestCase:
    description: str
    output_format: str
    expected_output: str
    expected_color_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ColumnLineageOutputTestCase:
    description: str
    output_format: str
    expected_output: str
    expected_color_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LargeColumnLineageOutputTestCase:
    description: str
    expected_included_fragment: str
    expected_excluded_fragment: str
    expected_summary_fragment: str
    expected_json_tip_fragment: str


@dataclass(frozen=True)
class LineageCompiledGraphRequirementTestCase:
    description: str
    targets: tuple[str, ...]
    select: tuple[str, ...]
    include_uses: bool
    expected_compiled_graph_required: bool


@dataclass(frozen=True)
class LineageFingerprintEnvironmentTestCase:
    description: str
    config: str
    environment_name: str
    first_value: str
    second_value: str
    expected_equal: bool


@dataclass(frozen=True)
class LineageFingerprintAvailabilityTestCase:
    description: str
    relative_path: str
    config: str
    expected_available: bool


@dataclass(frozen=True)
class LineagePathSelectorTestCase:
    description: str
    select: tuple[str, ...]
    expected_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class LineagePathSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class SharedSelectorParityTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class SharedSelectorErrorParityTestCase:
    description: str
    select: tuple[str, ...]
    expected_code: str


@dataclass(frozen=True)
class NormalizeLineageTargetTestCase:
    description: str
    target: str
    expected_target: str


@dataclass(frozen=True)
class NormalizeLineageTargetErrorTestCase:
    description: str
    target: str
    expected_code: str


@dataclass(frozen=True)
class SharedSelectorDepthTestCase:
    description: str
    select: tuple[str, ...]
    direction: str | None
    expected_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class FingerprintedFilesTestCase:
    """Authored files whose relation lineage fingerprint hashes exactly the expected inputs."""

    description: str
    files: dict[str, str]
    links: dict[str, str]
    unreadable_directories: tuple[str, ...]
    environment: dict[str, str]
    cli_vars: dict[str, object] | None
    expected_hashed_files: tuple[str, ...]
    expected_environment_names: tuple[str, ...]


@dataclass(frozen=True)
class UncacheableFingerprintTestCase:
    """Authored files whose relation lineage fingerprint is unavailable."""

    description: str
    files: dict[str, str]
    expected_fingerprint: None


@dataclass(frozen=True)
class InterruptedListingFingerprintTestCase:
    """A directory whose listing fails after it opened, under this Python's own `rglob`."""

    description: str
    files: dict[str, str]
    interrupted_directory: str
    expected_uncacheable_before: tuple[int, int]
