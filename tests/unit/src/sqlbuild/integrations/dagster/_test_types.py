from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagsterAssetSpecTestCase:
    description: str
    expected_asset_keys: tuple[tuple[str, ...], ...]
    expected_model_deps: tuple[tuple[str, ...], ...]
    expected_check_names: tuple[str, ...]
    expected_model_selector: str
    expected_check_selector: str
    expected_kinds_by_asset_key: tuple[tuple[tuple[str, ...], frozenset[str]], ...]
    expected_group_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterDecoratorTestCase:
    description: str
    expected_asset_keys: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DagsterScenarioCheckDecoratorTestCase:
    description: str
    expected_check_names: tuple[str, ...]
    unexpected_check_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterConflictingInputTestCase:
    description: str
    decorator_name: str
    expected_error_fragment: str
    expected_error_code: str


@dataclass(frozen=True)
class DagsterAssetCheckFilterTestCase:
    description: str
    expected_check_names: tuple[str, ...]
    unexpected_check_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterCliInvocationTestCase:
    description: str
    command_stdout: str
    command_stderr: str
    command_exit_code: int
    expected_success: bool
    expected_stdout: str
    expected_stderr: str


@dataclass(frozen=True)
class DagsterCliStreamTestCase:
    description: str
    command_stdout: str
    command_exit_code: int
    expected_asset_keys: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DagsterCliJsonStreamTestCase:
    description: str
    command_stdout: str
    selected_asset_keys: tuple[tuple[str, ...], ...]
    expected_asset_keys: tuple[tuple[str, ...], ...]
    expected_check_names: tuple[str, ...]
    expected_check_severities: tuple[str, ...]


@dataclass(frozen=True)
class DagsterCliFailureTestCase:
    description: str
    command_stderr: str
    command_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class DagsterCliSelectionTestCase:
    description: str
    selected_asset_keys: tuple[tuple[str, ...], ...]
    command_args: tuple[str, ...]
    expected_selectors: tuple[str, ...]
    expected_uses_select_file: bool
    expected_uses_json_output: bool


@dataclass(frozen=True)
class DagsterProjectPrepareTestCase:
    description: str
    command_stdout: str
    expected_dag_contents: str


@dataclass(frozen=True)
class DagsterProjectPrepareFailureTestCase:
    description: str
    command_stderr: str
    command_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class DagsterProjectDecoratorTestCase:
    description: str
    expected_asset_keys: tuple[tuple[str, ...], ...]
