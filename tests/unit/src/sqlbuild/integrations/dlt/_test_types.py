"""Shared test types for dlt integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DltLoaderDiscoveryTestCase:
    description: str
    expected_loader_names: tuple[str, ...]
    expected_relative_path: str
    expected_function_name: str


@dataclass(frozen=True)
class DltDestinationTestCase:
    description: str
    adapter_name: str
    connection_config: dict[str, object]
    dataset_name: str | None
    expected_destination_name: str
    expected_dataset_name: str | None
