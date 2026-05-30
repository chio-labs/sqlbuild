from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.types import PythonNodeKind


@dataclass(frozen=True)
class PythonLoaderNodeConversionTestCase:
    description: str
    expected_kind: PythonNodeKind
    expected_file_path: Path
    expected_relative_path: Path
    expected_name: str
    expected_depends_on: tuple[Callable[..., object], ...]
    expected_dependency_edges: tuple[tuple[str, str], ...]
    expected_target: str | None
    expected_write_strategy: str | None
    expected_cursor_column: str | None
    expected_unique_key: tuple[str, ...]
    expected_column_names: tuple[str, ...]
    expected_contract: str | None
    expected_connection_mode: LoaderConnectionMode


@dataclass(frozen=True)
class PythonNodeGraphInventoryTestCase:
    description: str
    expected_names: tuple[str, ...]
    expected_kinds: tuple[PythonNodeKind, ...]
    expected_typed_selectors: tuple[str, ...]
    expected_dependency_edges: tuple[tuple[str, str], ...]
    expected_task_tags: tuple[str, ...]
    expected_asset_column_names: tuple[str, ...]
    expected_check_severity: str
