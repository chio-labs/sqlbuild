from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.planner.models import ParsedSelector
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


@dataclass(frozen=True)
class PythonNodeSelectorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_names: frozenset[str]


@dataclass(frozen=True)
class PythonNodeParseSelectorTestCase:
    description: str
    raw: str
    expected_result: ParsedSelector


@dataclass(frozen=True)
class PythonNodeSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_type: type[Exception]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class PythonSqlSelectorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_sql_names: frozenset[str]
    expected_python_node_names: frozenset[str]


@dataclass(frozen=True)
class PythonSqlSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_type: type[Exception]
    expected_error_fragment: str | None = None
    python_graph_case: str = "default"
