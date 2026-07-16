from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.planner.models import ParsedSelector
from sqlbuild.compiler.python_nodes.models import PythonSqlRunSelection
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.python_nodes.models import SqlResourceRef


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
    expected_provider_usage_names: tuple[str, ...] = ()
    expected_provider_usage_parameters: tuple[str, ...] = ()
    expected_provider_usage_annotation_classes: tuple[str | None, ...] = ()
    expected_provider_usage_annotation_modules: tuple[str | None, ...] = ()


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
    sql_ref_dependency: SqlResourceRef | None = None


@dataclass(frozen=True)
class PythonSqlRunLifecycleTestCase:
    description: str
    python_graph_case: str
    selection: PythonSqlRunSelection
    expected_ingress_python_names: frozenset[str]
    expected_ingress_loader_names: frozenset[str]
    expected_read_side_python_names: frozenset[str]
    expected_read_side_sql_names: frozenset[str]


@dataclass(frozen=True)
class PythonNodeIdentityTestCase:
    description: str
    repo_files: dict[str, str]
    entry_module_path: str
    function_name: str
    node_type: str
    expected_source_path: str
    expected_dependency_qualnames: tuple[str, ...]
    expected_definition_fragments: tuple[str, ...]
    expected_metadata_fragments: tuple[str, ...]
    unexpected_metadata_fragments: tuple[str, ...] = ()
    extra_sys_paths: tuple[str, ...] = ()
    decorator_config: dict[str, object] | None = None


@dataclass(frozen=True)
class PythonNodeIdentityChangeTestCase:
    description: str
    before_repo_files: dict[str, str]
    after_repo_files: dict[str, str]
    entry_module_path: str
    function_name: str
    node_type: str
    expected_definition_hash_changed: bool
    expected_version_hash_changed: bool
    before_decorator_config: dict[str, object] | None = None
    after_decorator_config: dict[str, object] | None = None
