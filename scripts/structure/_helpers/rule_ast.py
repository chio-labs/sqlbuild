"""Shared AST helpers for structure convention checks."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from scripts.structure.constants import (
    ADAPTER_DOMAIN_NAME,
    ADAPTERS_PATH_MARKER,
    ALL_EXPORT_NAME,
    ANNOTATIONS_FUTURE_FEATURE_NAME,
    BARE_EXCEPTION_CLASS_NAME,
    CLASSES_PATH_MARKER,
    CLIENT_MODULE_NAME,
    CLIENT_STYLE_ROOT_PARTS,
    COMPILER_EXECUTOR_DOMAIN_NAMES,
    DBT_REF_ATTRIBUTE_NAME,
    ENTRY_MODULE_EXCLUDED_NAMES,
    EXCEPTIONS_MODULE_NAME,
    FROZEN_DATACLASS_KEYWORD_NAME,
    FUTURE_MODULE_NAME,
    HELPERS_PACKAGE_NAME,
    INIT_MODULE_NAME,
    INTEGRATIONS_ROOT_PARTS,
    LEGACY_DUCKDB_ADAPTER_PARTS,
    MAIN_MODULE_NAME,
    MAIN_PACKAGE_NAME,
    MODEL_CLASS_BASE_NAMES,
    NEWLINE_CHARACTER,
    NEWTYPE_CALL_NAME,
    ORCHESTRATION_INTEGRATION_NAMES,
    ORCHESTRATION_PUBLIC_MODULE_NAMES,
    PUBLIC_SURFACE_ROLE_NAMES,
    PYTHON_BYTECODE_CACHE_PACKAGE_NAME,
    PYTHON_FILE_SUFFIX,
    RAW_BUILTIN_RAISE_NAMES,
    RUNTIME_ROOT_PARTS,
    SELECTOR_MARKER,
    SELECTOR_STRING_METHOD_NAMES,
    SHARED_PACKAGE_NAME,
    SOURCE_ROOT_NAME,
    SQL_REFERENCE_KIND_CLASS_NAME,
    SQLBUILD_PACKAGE_NAME,
    TOOLING_ROOT_NAME,
    TYPE_CHECKING_NAME,
    TYPE_CLASS_BASE_NAMES,
)
from scripts.structure.models import Violation

_TARGET_REUSE_PATH_MARKERS: tuple[str, ...] = (
    "standard_reuse",
    "reuse_candidates.py",
    "reuse_execute.py",
    "reuse_plan.py",
    "reuse.py",
)
_WAREHOUSE_METADATA_METHODS: frozenset[str] = frozenset(
    {
        "list_relations",
        "relation_exists",
        "get_columns",
        "get_all_columns",
        "describe_relation",
        "schema_exists",
        "get_table_freshness_metadata",
        "get_tables_freshness_metadata",
        "query_column_names",
        "list_functions",
    }
)
_SC051_BATCHED_REASON_BY_PATH: dict[str, str] = {
    "src/sqlbuild/adapter/relations/main/relation_lookup.py": "single-query lookup capability",
    "src/sqlbuild/executor/janitor/_helpers/plan.py": "one list_relations per database",
    "src/sqlbuild/integrations/dbt/_helpers/planning/model_planning.py": (
        "one list_relations per database"
    ),
    "src/sqlbuild/compiler/planner/_helpers/output/plan_entry.py": (
        "one get_all_columns per database"
    ),
    "src/sqlbuild/integrations/dbt/_helpers/lineage/columns.py": (
        "one get_all_columns per selected dbt source/seed database-schema group"
    ),
    "src/sqlbuild/executor/pipeline/_helpers/testing.py": (
        "list_functions grouped per database, schema, and name batch"
    ),
    "src/sqlbuild/executor/run/_helpers/materializations/microbatch.py": (
        "schema-change get_columns gated to the first batch by schema_checked (delta is "
        "staged inside the loop); DML get_columns is per window by design"
    ),
    "src/sqlbuild/virtual/executor/_helpers/clone.py": (
        "destination existence is checked just-in-time under the per-model lease "
        "(concurrent hydrators); transient probe runs only on actual clones"
    ),
}
_GLOBAL_REUSE_FORBIDDEN_TERMS: tuple[str, ...] = (
    "source_fingerprint",
    "source_target_name",
    "source_connection",
    "target_cursor",
    "REUSE_RELATION",
    "reuse_relation",
)
_TARGET_REUSE_FORBIDDEN_TERMS: tuple[str, ...] = (
    "source_relation",
    "source relation",
    "source/target",
    "source_cursor",
    "target_relation",
    "target relation",
    "target_cursor",
)
_SC045_ALLOWED_PATH_MARKERS_BY_TERM: dict[str, tuple[str, ...]] = {
    "source_target_name": ("src/sqlbuild/compiler/planner/_helpers/warehouse/source_deferral.py",),
    "source_connection": (
        "src/sqlbuild/virtual/executor/_helpers/build.py",
        "src/sqlbuild/virtual/planner/main/plan.py",
    ),
}
_MAX_SOURCE_FILE_LINES: int = 2000
_MAX_HELPER_FLAT_MODULES: int = 11
_MAX_MAIN_FLAT_MODULES: int = 20
_MAX_MAIN_PUBLIC_FUNCTION_STATEMENTS: int = 40
_MAX_MAIN_PUBLIC_FUNCTION_DISTINCT_CALLS: int = 20
_MAX_MAIN_PUBLIC_FUNCTION_LOCALS: int = 20
_PARAMETER_MUTATION_METHODS: frozenset[str] = frozenset(
    {"add", "append", "clear", "extend", "insert", "pop", "remove", "setdefault", "update"}
)
_DISCARDED_CALL_VALIDATOR_PREFIXES: frozenset[str] = frozenset({"check_", "enforce_", "validate_"})
_DISCARDED_CALL_CALLBACK_PREFIXES: frozenset[str] = frozenset({"on_", "report_"})
_DISCARDED_CALL_DIAGNOSTIC_PREFIXES: frozenset[str] = frozenset({"log"})
_DISCARDED_CALL_WRITER_PREFIXES: frozenset[str] = frozenset({"write_"})
_DISCARDED_CALL_ALLOWED_NAMES: frozenset[str] = frozenset({"print"})
_PARAMETER_MUTATION_EXEMPT_PARAMETERS: frozenset[str] = frozenset({"cls", "self"})
_PARAMETER_MUTATION_ALLOW_COMMENT: str = "# sc: allow-param-mutation"
_MAIN_PHASE_REMEDIATION_MESSAGE: str = (
    "main/ public functions are orchestrators: they should read as an ordered list of "
    "named phases. Extract cohesive stages into _helpers/ functions that each accept "
    "explicit inputs and RETURN a named result model (no mutable threading), then call "
    "them in sequence. Do not create '_part_one'-style splits; name each phase after "
    "the result it produces (e.g. 'resolve_planner_scopes', 'detect_staleness')."
)
_MAIN_SUPPORT_FOLDER_NAMES: frozenset[str] = frozenset({"classes", "_helpers", "shared"})
_TOP_LEVEL_ROLE_FILE_ALLOWED_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("executor", "types.py"),
        ("python_nodes", "models.py"),
        ("python_nodes", "types.py"),
        ("spec", "constants.py"),
        ("spec", "models.py"),
        ("spec", "types.py"),
    }
)
_TOP_LEVEL_SUPPORT_PACKAGE_ALLOWED_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("executor", "_helpers"),
        ("spec", "_helpers"),
        ("virtual", "_helpers"),
    }
)
_MAX_SOURCE_LINE_ALLOWED_PATTERNS: tuple[str, ...] = (
    "src/sqlbuild/adapters/*/classes/*_adapter.py",
    "src/sqlbuild/adapter/contract/classes/base_adapter.py",
    "src/sqlbuild/adapter/contract/classes/duckdb_backed_adapter.py",
    "src/sqlbuild/virtual/state/classes/*.py",
)
_SC052_DBT_REF_SCAN_ALLOWED_PATHS: tuple[str, ...] = (
    "src/sqlbuild/integrations/dbt/_helpers/manifest/sqlbuild_refs.py",
    "src/sqlbuild/integrations/dbt/_helpers/manifest/compile_refs.py",
)
_SC054_SELECTOR_PLUS_PARSE_ALLOWED_PATHS: tuple[str, ...] = (
    "src/sqlbuild/compiler/planner/main/planning/selector_expansion.py",
)
_SC062_MACRO_LOAD_ALLOWED_PATHS: tuple[str, ...] = (
    "src/sqlbuild/compiler/compile/main/build_compile_inputs.py",
    "src/sqlbuild/compiler/compile/main/load_macros.py",
    "src/sqlbuild/compiler/compile/_helpers/render/macros.py",
)
_SC056_COMMENT_ALLOWED_PREFIXES: tuple[str, ...] = (
    "#!",
    "# -*-",
    "# coding:",
    "# noqa",
    "# type: ignore",
    "# pyright:",
    "# pylint:",
    "# pragma:",
    _PARAMETER_MUTATION_ALLOW_COMMENT,
)
_DOCSTRING_BEARING_NODE_TYPES: tuple[type[ast.AST], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)
_SOURCE_FRESHNESS_SINGULAR_WRITER_NAME: str = "write_source_freshness_record"
_SOURCE_FRESHNESS_INSERT_ALLOWED_MARKERS: tuple[str, ...] = (
    "scripts/structure/constants.py",
    "scripts/structure/rules/",
    "src/sqlbuild/adapter/",
    "src/sqlbuild/adapters/",
    "src/sqlbuild/virtual/state/classes/",
    "tests/",
)


def _is_sc045_term_allowed(*, path_text: str, term: str) -> bool:
    marker: str
    for marker in _SC045_ALLOWED_PATH_MARKERS_BY_TERM.get(term, ()):  # pragma: no branch
        if marker in path_text:
            return True
    return False


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _main_support_folder_violation(*, repo_root: Path, file_path: Path) -> Violation | None:
    relative_path: Path = file_path.resolve().relative_to(repo_root.resolve())
    parts: tuple[str, ...] = relative_path.parts
    index: int
    for index, part in enumerate(parts[:-1]):
        if (
            part == MAIN_PACKAGE_NAME
            and index + 1 < len(parts)
            and parts[index + 1] in _MAIN_SUPPORT_FOLDER_NAMES
        ):
            return Violation(
                code="SC061",
                path=file_path,
                line=None,
                message=(
                    "main package must not contain support folders like _helpers/, shared/, "
                    "or classes/; move support code beside main/"
                ),
            )
    return None


def _role_package_layout_violations(
    *,
    package_dir: Path,
    file_path: Path,
    package_name: str,
    mixed_code: str,
    too_many_code: str,
    module_label: str,
    max_flat_modules: int,
    ignored_subfolder_names: frozenset[str],
) -> list[Violation]:
    direct_modules: list[Path] = sorted(
        child
        for child in package_dir.glob("*.py")
        if child.name != INIT_MODULE_NAME and child.is_file()
    )
    concern_subfolders: list[Path] = sorted(
        child
        for child in package_dir.iterdir()
        if child.is_dir()
        and child.name != PYTHON_BYTECODE_CACHE_PACKAGE_NAME
        and child.name not in ignored_subfolder_names
    )

    violations: list[Violation] = []
    if direct_modules and concern_subfolders:
        violations.append(
            Violation(
                code=mixed_code,
                path=file_path,
                line=None,
                message=(
                    f"{package_name} package mixes flat {module_label} modules with "
                    "concern subfolders; use either flat files or move all modules into "
                    "subfolders"
                ),
            )
        )
    if len(direct_modules) > max_flat_modules:
        violations.append(
            Violation(
                code=too_many_code,
                path=file_path,
                line=None,
                message=(
                    f"{package_name} package has too many direct {module_label} modules "
                    f"({len(direct_modules)} > {max_flat_modules}); organize the "
                    f"entire {package_name} package into concern subfolders consistently, not just "
                    "one file"
                ),
            )
        )
    return violations


def _role_package_layout_dir(*, file_path: Path, package_name: str) -> Path | None:
    if file_path.parent.name == package_name:
        package_dir: Path = file_path.parent
    elif file_path.parent.parent.name == package_name:
        package_dir = file_path.parent.parent
    else:
        return None
    init_file: Path = package_dir / "__init__.py"
    if init_file.exists():
        return package_dir if file_path == init_file else None
    direct_modules: list[Path] = sorted(
        child
        for child in package_dir.glob("*.py")
        if child.name != INIT_MODULE_NAME and child.is_file()
    )
    if not direct_modules:
        return None
    return package_dir if file_path == direct_modules[0] else None


def _is_type_checking_import_block(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == TYPE_CHECKING_NAME
        and not node.orelse
        and all(isinstance(statement, (ast.Import, ast.ImportFrom)) for statement in node.body)
    )


def _is_adapter_implementation_file(file_path: Path) -> bool:
    path_text: str = file_path.as_posix()
    if ADAPTERS_PATH_MARKER in path_text and CLASSES_PATH_MARKER in path_text:
        return True
    if path_text.endswith("/adapter/contract/classes/duckdb_backed_adapter.py"):
        return True
    return path_text.endswith("/adapter/contract/classes/base_adapter.py")


def _path_is_allowed(*, path_text: str, allowed_paths: tuple[str, ...]) -> bool:
    return any(path_text.endswith(allowed_path) for allowed_path in allowed_paths)


def _compare_mentions_dbt_ref_kind(node: ast.Compare) -> bool:
    expressions: tuple[ast.expr, ...] = (node.left, *node.comparators)
    return any(_expression_is_dbt_ref_kind(expression) for expression in expressions)


def _expression_is_dbt_ref_kind(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return (
            node.attr == DBT_REF_ATTRIBUTE_NAME
            and _base_name(node.value) == SQL_REFERENCE_KIND_CLASS_NAME
        )
    return False


def _call_base_name(node: ast.Call) -> str | None:
    return _base_name(node.func)


def _is_selector_plus_string_method_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in SELECTOR_STRING_METHOD_NAMES:
        return False
    if not node.args:
        return False
    first_arg: ast.expr = node.args[0]
    return isinstance(first_arg, ast.Constant) and first_arg.value == SELECTOR_MARKER


def _docstring_bearing_nodes(module: ast.Module) -> tuple[ast.AST, ...]:
    return (
        module,
        *(node for node in ast.walk(module) if isinstance(node, _DOCSTRING_BEARING_NODE_TYPES)),
    )


def _statement_is_multiline_docstring(node: ast.stmt) -> bool:
    if not isinstance(node, ast.Expr):
        return False
    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
        return False
    end_lineno: int = getattr(node, "end_lineno", node.lineno)
    return end_lineno > node.lineno or NEWLINE_CHARACTER in node.value.value


def _metadata_call_label(
    *,
    node: ast.Call,
    bearing_method_names: frozenset[str],
    bearing_function_names: frozenset[str],
) -> str | None:
    if isinstance(node.func, ast.Attribute):
        if node.func.attr in _WAREHOUSE_METADATA_METHODS:
            return f".{node.func.attr}"
        if node.func.attr in bearing_method_names:
            return node.func.attr
        return None
    if isinstance(node.func, ast.Name) and node.func.id in bearing_function_names:
        return node.func.id
    return None


def _metadata_bearing_helper_names(
    *, module: ast.Module, parents: dict[ast.AST, ast.AST]
) -> tuple[frozenset[str], frozenset[str]]:
    method_calls_by_function: dict[ast.AST, set[str]] = {}
    function_calls_by_function: dict[ast.AST, set[str]] = {}
    directly_bearing: set[ast.AST] = set()
    method_names_by_function: dict[ast.AST, str] = {}
    function_names_by_function: dict[ast.AST, str] = {}

    definition: ast.AST
    for definition in ast.walk(module):
        if not isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        method_calls: set[str] = set()
        function_calls: set[str] = set()
        called: ast.AST
        for called in ast.walk(definition):
            if not isinstance(called, ast.Call):
                continue
            if isinstance(called.func, ast.Attribute):
                method_calls.add(called.func.attr)
                if called.func.attr in _WAREHOUSE_METADATA_METHODS:
                    directly_bearing.add(definition)
            elif isinstance(called.func, ast.Name):
                function_calls.add(called.func.id)
        method_calls_by_function[definition] = method_calls
        function_calls_by_function[definition] = function_calls
        if _is_method_definition(definition=definition, parents=parents):
            method_names_by_function[definition] = definition.name
        else:
            function_names_by_function[definition] = definition.name

    bearing: set[ast.AST] = set(directly_bearing)
    changed: bool = True
    while changed:
        changed = False
        bearing_method_names: set[str] = {
            method_names_by_function[fn] for fn in bearing if fn in method_names_by_function
        }
        bearing_function_names: set[str] = {
            function_names_by_function[fn] for fn in bearing if fn in function_names_by_function
        }
        function: ast.AST
        for function in method_calls_by_function:
            if function in bearing:
                continue
            if method_calls_by_function[function] & bearing_method_names or (
                function_calls_by_function[function] & bearing_function_names
            ):
                bearing.add(function)
                changed = True

    return (
        frozenset(method_names_by_function[fn] for fn in bearing if fn in method_names_by_function),
        frozenset(
            function_names_by_function[fn] for fn in bearing if fn in function_names_by_function
        ),
    )


def _is_method_definition(*, definition: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current: ast.AST = definition
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.ClassDef):
            return True
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
    return False


def _call_is_inside_loop(*, node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current: ast.AST = node
    while current in parents:
        current = parents[current]
        if isinstance(
            current, (ast.For, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            return True
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
    return False


def _private_assignment_target(node: ast.stmt) -> str | None:
    """Return the target name if node is a private module-level assignment, else None."""

    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        if node.target.id.startswith("_"):
            return node.target.id
    if isinstance(node, ast.Assign):
        target: ast.expr
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("_"):
                return target.id
    return None


def _is_within_same_helpers_package(
    *, current_package_parts: tuple[str, ...], imported_parts: tuple[str, ...]
) -> bool:
    if HELPERS_PACKAGE_NAME not in current_package_parts:
        return False
    helpers_index: int = current_package_parts.index(HELPERS_PACKAGE_NAME)
    helpers_prefix: tuple[str, ...] = current_package_parts[: helpers_index + 1]
    if imported_parts[: len(helpers_prefix)] != helpers_prefix:
        return False
    return len(current_package_parts) > helpers_index + 1 and len(imported_parts) > len(
        helpers_prefix
    )


def _has_deep_internal_segment(
    *, parts: tuple[str, ...], internal_segments: frozenset[str]
) -> bool:
    """Check whether any segment in the import path is a deep internal boundary."""

    return any(seg in internal_segments for seg in parts)


def _is_runtime_file(*, repo_root: Path, file_path: Path) -> bool:
    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    runtime_module_path_part_count: int = 3
    return (
        len(relative_parts) >= runtime_module_path_part_count
        and relative_parts[:2] == RUNTIME_ROOT_PARTS
    )


def _is_allowed_reexport_surface(*, repo_root: Path, file_path: Path) -> bool:
    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if file_path.name == INIT_MODULE_NAME:
        return True
    top_level_runtime_module_part_count: int = 3
    integration_module_part_count: int = 4
    if (
        len(relative_parts) == top_level_runtime_module_part_count
        and relative_parts[:2] == RUNTIME_ROOT_PARTS
    ):
        return True
    if (
        len(relative_parts) >= integration_module_part_count
        and relative_parts[:3] == INTEGRATIONS_ROOT_PARTS
    ):
        return True
    if (
        len(relative_parts) == integration_module_part_count
        and relative_parts[3] == EXCEPTIONS_MODULE_NAME
    ):
        return True
    return False


def _is_pure_reexport_module(module: ast.Module) -> bool:
    saw_import: bool = False
    saw_all: bool = False
    for node in module.body:
        if _is_module_docstring(node) or _is_future_annotations_import(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            saw_import = True
            continue
        if _is_all_assignment(node):
            saw_all = True
            continue
        return False
    return saw_import and saw_all


def _is_module_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_future_annotations_import(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.ImportFrom)
        and node.module == FUTURE_MODULE_NAME
        and any(alias.name == ANNOTATIONS_FUTURE_FEATURE_NAME for alias in node.names)
    )


def _is_all_assignment(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name) and target.id == ALL_EXPORT_NAME for target in node.targets
        )
    return (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == ALL_EXPORT_NAME
    )


def _adapter_contract_class_names(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> frozenset[str]:
    indexed_names: frozenset[str] = _builtin_adapter_contract_class_names_by_path(
        repo_root=repo_root
    ).get(file_path.resolve(), frozenset())
    if indexed_names:
        return indexed_names

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if relative_parts[:3] not in CLIENT_STYLE_ROOT_PARTS:
        return frozenset()
    if file_path.name != CLIENT_MODULE_NAME and relative_parts[-3:] != LEGACY_DUCKDB_ADAPTER_PARTS:
        return frozenset()
    return frozenset(
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Adapter")
    )


def _builtin_adapter_contract_class_names_by_path(*, repo_root: Path) -> dict[Path, frozenset[str]]:
    try:
        from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
        from sqlbuild.adapter.discovery.main.builtins import builtin_adapter_classes
    except ImportError:
        return {}

    repo_root = repo_root.resolve()
    names_by_path: dict[Path, set[str]] = {}
    adapter_cls: type[object]
    for adapter_cls in builtin_adapter_classes().values():
        for cls in adapter_cls.__mro__:
            if cls is BaseAdapter or cls is object:
                break
            source_path_text: str | None = inspect.getsourcefile(cls)
            if source_path_text is None:
                continue
            source_path: Path = Path(source_path_text).resolve()
            try:
                source_path.relative_to(repo_root)
            except ValueError:
                continue
            names_by_path.setdefault(source_path, set()).add(cls.__name__)
    return {path: frozenset(names) for path, names in names_by_path.items()}


def _strict_adapter_contract_method_names() -> frozenset[str]:
    try:
        from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
    except Exception:
        return frozenset()

    return frozenset(getattr(StrictAdapter, "__abstractmethods__", frozenset()))


def _is_base_adapter_method_alias(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return isinstance(node.value, ast.Attribute) and _is_name(
            node=node.value.value, name="BaseAdapter"
        )
    if isinstance(node, ast.AnnAssign):
        return (
            node.value is not None
            and isinstance(node.value, ast.Attribute)
            and _is_name(node=node.value.value, name="BaseAdapter")
        )
    return False


def _is_super_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_name(node=node.func, name="super")


def _is_name(*, node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def is_docstring_only_module(module: ast.Module) -> bool:
    """Return whether the module body is empty or docstring-only."""

    body: list[ast.stmt] = module.body
    if not body:
        return True
    if len(body) != 1:
        return False
    return _is_string_expr(body[0])


def _non_docstring_body(module: ast.Module) -> list[ast.stmt]:
    if module.body and _is_string_expr(module.body[0]):
        return module.body[1:]
    return list(module.body)


def _is_entry_module(file_path: Path) -> bool:
    return (
        file_path.suffix == PYTHON_FILE_SUFFIX
        and file_path.name not in ENTRY_MODULE_EXCLUDED_NAMES
        and file_path.parent.name == MAIN_PACKAGE_NAME
    )


def _is_direct_child_of_helpers_root(file_path: Path) -> bool:
    parts: tuple[str, ...] = file_path.parts
    if HELPERS_PACKAGE_NAME not in parts[:-1]:
        return False
    helpers_index: int = parts.index(HELPERS_PACKAGE_NAME)
    return len(parts) == helpers_index + 2


def _is_string_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_allowed_type_class(node: ast.ClassDef) -> bool:
    if _is_dataclass_class(node) or _inherits_from_base_names(
        node=node, base_names=MODEL_CLASS_BASE_NAMES
    ):
        return False
    return _inherits_from_base_names(node=node, base_names=TYPE_CLASS_BASE_NAMES)


def _is_allowed_model_class(node: ast.ClassDef) -> bool:
    if node.name.startswith("_"):
        return False
    return _is_dataclass_class(node) or _inherits_from_base_names(
        node=node, base_names=MODEL_CLASS_BASE_NAMES
    )


def _is_exception_class(node: ast.ClassDef) -> bool:
    """Return whether a class definition looks like a custom exception."""

    if node.name.endswith(("Error", "Exception")):
        return True

    base_names: list[str | None] = []
    for base in node.bases:
        base_names.append(_base_name(base))
    return any((base_name or "").endswith(("Error", "Exception")) for base_name in base_names)


def _is_dataclass_class(node: ast.ClassDef) -> bool:
    return any(
        _decorator_name(decorator).endswith("dataclass") for decorator in node.decorator_list
    )


def _dataclass_is_frozen(node: ast.ClassDef) -> bool:
    decorator: ast.expr
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and _decorator_name(decorator.func).endswith(
            "dataclass"
        ):
            keyword: ast.keyword
            for keyword in decorator.keywords:
                if keyword.arg == FROZEN_DATACLASS_KEYWORD_NAME and isinstance(
                    keyword.value, ast.Constant
                ):
                    return keyword.value.value is True
            return False
    return False


def _is_main_package_module(file_path: Path) -> bool:
    return (
        file_path.suffix == PYTHON_FILE_SUFFIX
        and file_path.name != INIT_MODULE_NAME
        and MAIN_PACKAGE_NAME in file_path.parts[:-1]
    )


def _top_level_function_nodes(
    module: ast.Module,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    return tuple(
        node
        for node in _non_docstring_body(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _distinct_callee_names(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    names: set[str] = set()
    node: ast.AST
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        name: str | None = _call_name(node)
        if name is not None:
            names.add(name)
    return frozenset(names)


def _assigned_local_names(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    names: set[str] = set()
    node: ast.AST
    for node in ast.walk(function_node):
        if isinstance(node, ast.Assign):
            target: ast.expr
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return frozenset(names)


def _discarded_call_is_allowed(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Name):
        return True
    name: str = node.func.id.lstrip("_")
    if name in _DISCARDED_CALL_ALLOWED_NAMES:
        return True
    allowed_prefixes: tuple[str, ...] = (
        *_DISCARDED_CALL_VALIDATOR_PREFIXES,
        *_DISCARDED_CALL_CALLBACK_PREFIXES,
        *_DISCARDED_CALL_DIAGNOSTIC_PREFIXES,
        *_DISCARDED_CALL_WRITER_PREFIXES,
    )
    return any(name.startswith(prefix) for prefix in allowed_prefixes)


def _call_display_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        base_name: str | None = _base_name(node.func.value)
        if base_name is None:
            return node.func.attr
        return f"{base_name}.{node.func.attr}"
    return "<call>"


def _is_compiler_or_executor_helper_module(*, repo_root: Path, file_path: Path) -> bool:
    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    nested_helper_module_part_count: int = 5
    return (
        len(relative_parts) >= nested_helper_module_part_count
        and relative_parts[:2] == RUNTIME_ROOT_PARTS
        and relative_parts[2] in COMPILER_EXECUTOR_DOMAIN_NAMES
        and HELPERS_PACKAGE_NAME in relative_parts[3:-1]
        and file_path.suffix == PYTHON_FILE_SUFFIX
    )


def _function_parameter_names(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> frozenset[str]:
    return frozenset(
        arg.arg
        for arg in (
            *function_node.args.posonlyargs,
            *function_node.args.args,
            *function_node.args.kwonlyargs,
        )
        if arg.arg not in _PARAMETER_MUTATION_EXEMPT_PARAMETERS
    )


def _parameter_mutated_by_node(*, node: ast.AST, parameter_names: frozenset[str]) -> str | None:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return _parameter_mutated_by_assignment(node=node, parameter_names=parameter_names)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr not in _PARAMETER_MUTATION_METHODS:
            return None
        return _root_parameter_name(node=node.func.value, parameter_names=parameter_names)
    return None


def _parameter_mutated_by_assignment(
    *, node: ast.Assign | ast.AnnAssign | ast.AugAssign, parameter_names: frozenset[str]
) -> str | None:
    targets: tuple[ast.expr, ...]
    if isinstance(node, ast.Assign):
        targets = tuple(node.targets)
    else:
        targets = (node.target,)
    target: ast.expr
    for target in targets:
        parameter_name: str | None = _root_parameter_name(
            node=target, parameter_names=parameter_names
        )
        if parameter_name is not None and not isinstance(target, ast.Name):
            return parameter_name
    return None


def _root_parameter_name(*, node: ast.AST, parameter_names: frozenset[str]) -> str | None:
    if isinstance(node, ast.Name):
        return node.id if node.id in parameter_names else None
    if isinstance(node, ast.Attribute):
        return _root_parameter_name(node=node.value, parameter_names=parameter_names)
    if isinstance(node, ast.Subscript):
        return _root_parameter_name(node=node.value, parameter_names=parameter_names)
    return None


def _line_allows_parameter_mutation(*, source_lines: list[str], line_number: int) -> bool:
    if line_number < 1 or line_number > len(source_lines):
        return False
    return _PARAMETER_MUTATION_ALLOW_COMMENT in source_lines[line_number - 1]


def _inherits_from_base_names(*, node: ast.ClassDef, base_names: frozenset[str]) -> bool:
    return any(_base_name(base) in base_names for base in node.bases)


def _is_local_model_union_alias(
    *, file_path: Path, module: ast.Module, node: ast.TypeAlias
) -> bool:
    if not _is_within_role_package(file_path=file_path, role_directory_name="models"):
        return False

    model_class_names: frozenset[str] = frozenset(
        child.name
        for child in _non_docstring_body(module)
        if isinstance(child, ast.ClassDef) and _is_allowed_model_class(child)
    )
    if not model_class_names:
        return False

    union_member_names: tuple[str, ...] | None = _local_union_member_names(node.value)
    if union_member_names is None:
        return False
    union_member_count: int = 2
    if len(union_member_names) < union_member_count:
        return False
    return all(name in model_class_names for name in union_member_names)


def _is_private_type_alias(node: ast.TypeAlias) -> bool:
    return isinstance(node.name, ast.Name) and node.name.id.startswith("_")


def _local_union_member_names(node: ast.expr) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left_names: tuple[str, ...] | None = _local_union_member_names(node.left)
        right_names: tuple[str, ...] | None = _local_union_member_names(node.right)
        if left_names is None or right_names is None:
            return None
        return (*left_names, *right_names)
    return None


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


def _is_runtime_source_file(file_path: Path) -> bool:
    parts: tuple[str, ...] = file_path.parts
    return (
        SOURCE_ROOT_NAME in parts
        and SQLBUILD_PACKAGE_NAME in parts
        and file_path.suffix == PYTHON_FILE_SUFFIX
    )


def _raise_uses_raw_builtin(node: ast.Raise) -> bool:
    if node.exc is None:
        return False
    raised_name: str | None = (
        _base_name(node.exc.func) if isinstance(node.exc, ast.Call) else _base_name(node.exc)
    )
    return raised_name in RAW_BUILTIN_RAISE_NAMES


def _is_bare_exception_handler(node: ast.ExceptHandler) -> bool:
    return (
        node.name is None
        and isinstance(node.type, ast.Name)
        and node.type.id == BARE_EXCEPTION_CLASS_NAME
    )


def _handler_body_is_single_swallow(body: list[ast.stmt]) -> bool:
    if len(body) != 1:
        return False

    statement: ast.stmt = body[0]
    if isinstance(statement, ast.Continue):
        return True
    if not isinstance(statement, ast.Return):
        return False
    return _is_swallowed_probe_return_value(statement.value)


def _is_swallowed_probe_return_value(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Constant):
        return node.value is None or node.value is False
    if isinstance(node, ast.Dict):
        return not node.keys and not node.values
    if isinstance(node, ast.Tuple):
        return not node.elts
    return False


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent: str = _decorator_name(node.value)
        return node.attr if not parent else f"{parent}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _is_newtype_assignment(node: ast.AST) -> bool:
    value: ast.expr | None = None
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        value = node.value
    elif (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
    ):
        value = node.value

    if not isinstance(value, ast.Call):
        return False

    return _base_name(value.func) == NEWTYPE_CALL_NAME


def _is_within_role_package(*, file_path: Path, role_directory_name: str) -> bool:
    return role_directory_name in file_path.parts[:-1]


def _is_direct_child_of_main_package(relative_parts: tuple[str, ...]) -> bool:
    parent_and_module_part_count: int = 2
    return (
        len(relative_parts) >= parent_and_module_part_count
        and relative_parts[-2] == MAIN_PACKAGE_NAME
        and relative_parts[-1] != MAIN_MODULE_NAME
    )


def _is_within_main_package(relative_parts: tuple[str, ...]) -> bool:
    return MAIN_PACKAGE_NAME in relative_parts[2:-1] and relative_parts[-1] != MAIN_MODULE_NAME


def _is_orchestration_integration_public_module(relative_parts: tuple[str, ...]) -> bool:
    integration_public_module_part_count: int = 5
    return (
        len(relative_parts) == integration_public_module_part_count
        and relative_parts[:3] == INTEGRATIONS_ROOT_PARTS
        and relative_parts[3] in ORCHESTRATION_INTEGRATION_NAMES
        and relative_parts[-1] in ORCHESTRATION_PUBLIC_MODULE_NAMES
    )


def _is_orchestration_integration_public_init(file_path: Path) -> bool:
    parts: tuple[str, ...] = file_path.parts
    integration_public_path_part_count: int = 5
    return (
        len(parts) >= integration_public_path_part_count
        and parts[-5:-2] == INTEGRATIONS_ROOT_PARTS
        and parts[-2] in ORCHESTRATION_INTEGRATION_NAMES
        and parts[-1] == INIT_MODULE_NAME
    )


def _is_orchestration_integration_public_entry(file_path: Path) -> bool:
    parts: tuple[str, ...] = file_path.parts
    integration_public_path_part_count: int = 5
    return (
        len(parts) >= integration_public_path_part_count
        and parts[-5:-2] == INTEGRATIONS_ROOT_PARTS
        and parts[-2] in ORCHESTRATION_INTEGRATION_NAMES
    )


def _subpackage_parts(*, repo_root: Path, file_path: Path) -> tuple[str, ...]:
    relative_parts: tuple[str, ...] = (
        file_path.resolve().relative_to(repo_root.resolve()).with_suffix("").parts
    )

    runtime_module_path_part_count: int = 4
    script_module_path_part_count: int = 3
    if (
        len(relative_parts) >= runtime_module_path_part_count
        and relative_parts[:2] == RUNTIME_ROOT_PARTS
    ):
        package_parts: tuple[str, ...] = relative_parts[1:-1]
    elif (
        len(relative_parts) >= script_module_path_part_count
        and relative_parts[0] == TOOLING_ROOT_NAME
    ):
        package_parts = relative_parts[:-1]
    else:
        return ()

    return tuple(package_parts)


def _is_forbidden_shared_import(
    *,
    parent_package_parts: tuple[str, ...],
    imported_parts: tuple[str, ...],
) -> bool:
    if imported_parts[: len(parent_package_parts)] != parent_package_parts:
        return False
    if len(imported_parts) <= len(parent_package_parts):
        return False

    next_segment: str = imported_parts[len(parent_package_parts)]
    if next_segment == SHARED_PACKAGE_NAME:
        return False

    return len(imported_parts) > len(parent_package_parts) + 1


def _is_allowed_sibling_public_surface(
    *,
    parent_package_parts: tuple[str, ...],
    imported_parts: tuple[str, ...],
) -> bool:
    if (
        parent_package_parts[-1] == MAIN_PACKAGE_NAME
        and len(imported_parts) == len(parent_package_parts) + 2
    ):
        return True
    if (
        len(imported_parts) == len(parent_package_parts) + 2
        and imported_parts[len(parent_package_parts)] == MAIN_PACKAGE_NAME
        and imported_parts[-1] != MAIN_PACKAGE_NAME
    ):
        return True
    if (
        len(imported_parts) == len(parent_package_parts) + 3
        and imported_parts[len(parent_package_parts)] == MAIN_PACKAGE_NAME
        and imported_parts[-1] != MAIN_PACKAGE_NAME
    ):
        return True
    if (
        len(imported_parts) == len(parent_package_parts) + 2
        and imported_parts[len(parent_package_parts)] in PUBLIC_SURFACE_ROLE_NAMES
    ):
        return True
    if (
        len(imported_parts) == len(parent_package_parts) + 3
        and imported_parts[len(parent_package_parts) + 1] in PUBLIC_SURFACE_ROLE_NAMES
    ):
        return True
    if len(imported_parts) != len(parent_package_parts) + 2:
        return False

    public_module_name: str = imported_parts[-1]
    if public_module_name in PUBLIC_SURFACE_ROLE_NAMES:
        return True
    if ADAPTER_DOMAIN_NAME in parent_package_parts:
        return True
    return False
