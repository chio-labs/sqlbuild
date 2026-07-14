"""Shared test types for dlt integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.contract.types import BuiltinAdapter


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
    destination_config: dict[str, object] | None = None
    expected_config_params: dict[str, object] = field(default_factory=dict)
    expected_caps_params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DltDestinationErrorTestCase:
    description: str
    adapter_name: str
    connection_config: dict[str, object]
    dataset_name: str | None
    expected_error_fragment: str
    destination_config: dict[str, object] | None = None


@dataclass(frozen=True)
class DltDestinationCoverageTestCase:
    description: str
    expected_adapters: frozenset[BuiltinAdapter]


@dataclass(frozen=True)
class DltProgressCollectorTestCase:
    description: str
    updates: tuple[tuple[str, str, int, int | None], ...]
    expected_fragments: tuple[str, ...]
    expected_live_fragments: tuple[str, ...]
