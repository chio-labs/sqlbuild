"""Shared test types for ingestr integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestrCommandTestCase:
    description: str
    adapter_name: str
    connection_config: dict[str, object]
    expected_command: tuple[str, ...]


@dataclass(frozen=True)
class IngestrLoaderDiscoveryTestCase:
    description: str
    repo_files: dict[str, str]
    expected_loader_names: tuple[str, ...]
    expected_relative_paths: tuple[str, ...]


@dataclass(frozen=True)
class IngestrRunnerTestCase:
    description: str
    returncode: int
    expected_signal_number: int
    expected_event_types: tuple[str, ...] = ()
