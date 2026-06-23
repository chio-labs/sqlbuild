from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DbtProfileRenderTestCase:
    description: str
    output: dict[str, object]
    env: dict[str, str]
    expected_output: dict[str, object]


@dataclass(frozen=True)
class DbtProfileRenderErrorTestCase:
    description: str
    output: dict[str, object]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtProfileInitTomlTestCase:
    description: str
    secret_value: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtProfileInitDiscoveryTestCase:
    description: str
    expected_profiles_dir_fragment: str


@dataclass(frozen=True)
class DbtProfileNormalizeTestCase:
    description: str
    output: dict[str, object]
    expected_adapter: str
    expected_connection: dict[str, object]
    expected_target_schema: str | None
    expected_target_database: str | None


@dataclass(frozen=True)
class DbtProfileNormalizeErrorTestCase:
    description: str
    output: dict[str, object]
    expected_error_fragment: str
