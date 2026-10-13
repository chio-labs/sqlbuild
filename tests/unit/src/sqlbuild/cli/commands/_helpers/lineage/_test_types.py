from __future__ import annotations

from dataclasses import dataclass


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
class FingerprintedFilesTestCase:
    """Authored files whose relation lineage fingerprint hashes exactly the expected inputs."""

    description: str
    files: dict[str, str]
    links: dict[str, str]
    unreadable_directories: tuple[str, ...]
    environment: dict[str, str]
    cli_vars: dict[str, object]
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
