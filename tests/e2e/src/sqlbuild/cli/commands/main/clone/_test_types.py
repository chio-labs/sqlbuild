from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloneE2ETestCase:
    description: str
    repo_files: dict[str, str]
    clone_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class ClonePolicyErrorTestCase:
    description: str
    origin_allowed: bool
    destination_allowed: bool
    expected_error_code: str
    expected_policy_key: str


@dataclass(frozen=True)
class VirtualCloneE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_registered_artifacts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CloneFunctionGraphE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_resource_order: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class ClonePythonFunctionE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_unregistered_function_match: str


@dataclass(frozen=True)
class CloneDeferredSourceFunctionE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
