"""Rule implementations for structure convention checks."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.structure._helpers.rule_ast import (
    _adapter_contract_class_names,
    _has_deep_internal_segment,
    _is_allowed_sibling_public_surface,
    _is_allowed_type_class,
    _is_base_adapter_method_alias,
    _is_dataclass_class,
    _is_direct_child_of_helpers_root,
    _is_entry_module,
    _is_exception_class,
    _is_forbidden_shared_import,
    _is_local_model_union_alias,
    _is_newtype_assignment,
    _is_orchestration_integration_public_entry,
    _is_private_type_alias,
    _is_super_call,
    _is_within_main_package,
    _is_within_role_package,
    _is_within_same_helpers_package,
    _non_docstring_body,
    _private_assignment_target,
    _strict_adapter_contract_method_names,
    _subpackage_parts,
)
from scripts.structure.constants import (
    ADAPTER_ENTRY_BOUNDARY_NAMES,
    ADAPTER_ENTRY_BYPASS_MODULE_NAMES,
    ADAPTER_ROOT_PARTS,
    CLASSES_MODULE_NAME,
    CLASSES_PACKAGE_NAME,
    CLIENT_MODULE_NAME,
    CLIENT_STYLE_ROOT_PARTS,
    CONSTANTS_MODULE_NAME,
    CROSS_PACKAGE_PUBLIC_MODULE_NAMES,
    CROSS_PACKAGE_SOURCE_EXEMPT_DOMAIN_NAMES,
    CROSS_PACKAGE_TARGET_EXEMPT_DOMAIN_NAMES,
    DEEP_INTERNAL_PACKAGE_NAMES,
    ENTRY_PACKAGE_NAME,
    EXCEPTIONS_MODULE_NAME,
    EXCEPTIONS_PACKAGE_NAME,
    HELPERS_MODULE_NAME,
    HELPERS_PACKAGE_NAME,
    INIT_MODULE_NAME,
    MAIN_MODULE_NAME,
    MAIN_PACKAGE_NAME,
    MAIN_SUPPORT_IMPORT_PACKAGE_NAMES,
    RUNTIME_ROOT_PARTS,
    SC010_CODE,
    SHARED_PACKAGE_NAME,
    SIBLING_HELPER_IMPORTER_PACKAGE_NAMES,
    SQLBUILD_PACKAGE_NAME,
    TYPES_MODULE_NAME,
    TYPES_PACKAGE_NAME,
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
    "src/sqlbuild/adapter/main/relation_lookup.py": "single-query lookup capability",
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
        ("adapter", "constants.py"),
        ("adapter", "models.py"),
        ("adapter", "types.py"),
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
        ("adapter", "classes"),
        ("adapter", "_helpers"),
        ("executor", "_helpers"),
        ("spec", "_helpers"),
        ("virtual", "_helpers"),
    }
)
_MAX_SOURCE_LINE_ALLOWED_PATTERNS: tuple[str, ...] = (
    "src/sqlbuild/adapters/*/classes/*_adapter.py",
    "src/sqlbuild/adapter/classes/base_adapter.py",
    "src/sqlbuild/adapter/classes/duckdb_backed_adapter.py",
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
    "scripts/structure/_helpers/",
    "src/sqlbuild/adapter/",
    "src/sqlbuild/adapters/",
    "src/sqlbuild/virtual/state/classes/",
    "tests/",
)


def check_classes_module_name(file_path: Path) -> list[Violation]:
    """Reject classes.py in favor of a classes/ package."""

    if file_path.name != CLASSES_MODULE_NAME:
        return []

    return [
        Violation(
            code="SC005",
            path=file_path,
            line=None,
            message="use a classes/ package instead of classes.py",
        )
    ]


def check_classes_package_module_shape(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Require runtime classes/ modules to define exactly one class."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    nested_classes_module_part_count: int = 5
    if (
        len(relative_parts) < nested_classes_module_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    if CLASSES_PACKAGE_NAME not in relative_parts[2:-1] or file_path.name == INIT_MODULE_NAME:
        return []

    class_nodes: list[ast.ClassDef] = [
        node for node in module.body if isinstance(node, ast.ClassDef)
    ]
    if len(class_nodes) == 1:
        return []
    return [
        Violation(
            code="SC043",
            path=file_path,
            line=1,
            message="runtime classes/ modules must define exactly one class",
        )
    ]


def check_private_definition_ordering(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject private dataclasses and constants that appear after function definitions."""

    violations: list[Violation] = []
    first_function_line: int | None = None
    node: ast.stmt
    for node in module.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and first_function_line is None
        ):
            first_function_line = node.lineno
        if first_function_line is None:
            continue
        if (
            isinstance(node, ast.ClassDef)
            and node.name.startswith("_")
            and _is_dataclass_class(node)
        ):
            violations.append(
                Violation(
                    code="SC034",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "private dataclass definitions must appear before "
                        "function definitions at module level"
                    ),
                )
            )
        private_target: str | None = _private_assignment_target(node)
        if private_target is not None:
            violations.append(
                Violation(
                    code="SC034",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "private constant definitions must appear before "
                        "function definitions at module level"
                    ),
                )
            )
    return violations


def check_type_declarations_outside_types(
    *, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject type-layer declarations outside types.py."""

    if file_path.name == TYPES_MODULE_NAME or _is_within_role_package(
        file_path=file_path, role_directory_name=TYPES_PACKAGE_NAME
    ):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and _is_allowed_type_class(node):
            if node.name.startswith("_") and _is_within_role_package(
                file_path=file_path, role_directory_name=HELPERS_PACKAGE_NAME
            ):
                continue
            violations.append(
                Violation(
                    code="SC015",
                    path=file_path,
                    line=node.lineno,
                    message="type-layer declarations must be defined in types.py",
                )
            )
            continue

        if (
            isinstance(node, ast.TypeAlias)
            and not _is_private_type_alias(node)
            and not _is_local_model_union_alias(
                file_path=file_path,
                module=module,
                node=node,
            )
        ):
            violations.append(
                Violation(
                    code="SC015",
                    path=file_path,
                    line=node.lineno,
                    message="type-layer declarations must be defined in types.py",
                )
            )
            continue

        if isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_newtype_assignment(node):
            violations.append(
                Violation(
                    code="SC015",
                    path=file_path,
                    line=node.lineno,
                    message="type-layer declarations must be defined in types.py",
                )
            )
    return violations


def check_exception_declarations_outside_exceptions(
    *, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject custom exception declarations outside exceptions.py."""

    if file_path.name == EXCEPTIONS_MODULE_NAME or _is_within_role_package(
        file_path=file_path, role_directory_name=EXCEPTIONS_PACKAGE_NAME
    ):
        if _is_direct_child_of_helpers_root(file_path):
            return [
                Violation(
                    code="SC021",
                    path=file_path,
                    line=1,
                    message=(
                        "custom exceptions must not live under _helpers/; "
                        "define them in a top-level exceptions.py or exceptions/ boundary"
                    ),
                )
            ]
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and _is_exception_class(node):
            violations.append(
                Violation(
                    code="SC021",
                    path=file_path,
                    line=node.lineno,
                    message="custom exceptions must be defined in exceptions.py or exceptions/",
                )
            )
    return violations


def check_constants_outside_constants(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject uppercase module-level constant assignments outside constants.py."""

    if file_path.name == CONSTANTS_MODULE_NAME:
        return []

    violations: list[Violation] = []
    for node in _non_docstring_body(module):
        targets: list[str] = []
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        else:
            continue

        for target_name in targets:
            if target_name.startswith("_"):
                continue
            if target_name.isupper():
                violations.append(
                    Violation(
                        code="SC016",
                        path=file_path,
                        line=node.lineno,
                        message="module-level uppercase constants must be defined in constants.py",
                    )
                )
    return violations


def check_helpers_package_shape(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Keep _helpers/ shallow and free of generic entrypoints."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if HELPERS_PACKAGE_NAME not in relative_parts[:-1]:
        return []

    helpers_index: int = relative_parts.index(HELPERS_PACKAGE_NAME)
    if len(relative_parts) == helpers_index + 2 and file_path.name != MAIN_MODULE_NAME:
        return []
    if len(relative_parts) == helpers_index + 3 and file_path.name != MAIN_MODULE_NAME:
        return []

    code: str = "SC010" if len(relative_parts) == helpers_index + 2 else "SC022"
    message: str = (
        "_helpers/ must not contain main.py; keep orchestration outside helper packages"
        if code == SC010_CODE
        else (
            "helper subpackages must stay shallow and use direct role-oriented files; "
            "main.py and nested subpackages are not allowed under scoped helpers"
        )
    )

    return [
        Violation(
            code=code,
            path=file_path,
            line=None,
            message=message,
        )
    ]


def check_shared_package_structure(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject orchestration entrypoints inside shared/ packages."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if SHARED_PACKAGE_NAME not in relative_parts[:-1]:
        return []
    shared_index: int = relative_parts.index(SHARED_PACKAGE_NAME)
    if (
        len(relative_parts) > shared_index + 2
        and HELPERS_PACKAGE_NAME in relative_parts[shared_index + 1 : -1]
    ):
        return []
    if file_path.name != MAIN_MODULE_NAME:
        return []

    return [
        Violation(
            code="SC012",
            path=file_path,
            line=None,
            message=(
                "shared/ must not contain main.py; keep shared packages limited to support code"
            ),
        )
    ]


def check_integrations_package_structure(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Enforce client.py instead of main.py within client-style packages."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    shared_package_module_part_count: int = 5
    if (
        len(relative_parts) < shared_package_module_part_count
        or relative_parts[:3] not in CLIENT_STYLE_ROOT_PARTS
    ):
        return []
    if file_path.name != MAIN_MODULE_NAME:
        return []

    return [
        Violation(
            code="SC023",
            path=file_path,
            line=None,
            message=(
                "client-style packages must use client.py instead of main.py for primary client "
                "entrypoints"
            ),
        )
    ]


def check_adapter_class_entry_module_shape(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Enforce focused single-class entry modules within adapter/ subpackages."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    adapter_class_module_part_count: int = 6
    if (
        len(relative_parts) < adapter_class_module_part_count
        or relative_parts[:3] != ADAPTER_ROOT_PARTS
    ):
        return []
    if _is_within_main_package(relative_parts):
        return []
    if file_path.name.startswith("_") or file_path.name in ADAPTER_ENTRY_BYPASS_MODULE_NAMES:
        return []
    if any(part in ADAPTER_ENTRY_BOUNDARY_NAMES for part in relative_parts[3:-1]):
        return []

    public_class_nodes: list[ast.ClassDef] = [
        node
        for node in _non_docstring_body(module)
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]
    violations: list[Violation] = []

    if len(public_class_nodes) != 1:
        violations.append(
            Violation(
                code="SC031",
                path=file_path,
                line=1,
                message=(
                    "adapter class entry modules must define exactly one public top-level class"
                ),
            )
        )

    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)):
            continue
        violations.append(
            Violation(
                code="SC032",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message=(
                    "adapter class entry modules must contain only imports and top-level classes"
                ),
            )
        )

    return violations


def check_client_module_shape(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Enforce focused single-class client.py modules within client-style packages."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    client_module_path_part_count: int = 5
    if (
        file_path.name != CLIENT_MODULE_NAME
        or len(relative_parts) < client_module_path_part_count
        or relative_parts[:3] not in CLIENT_STYLE_ROOT_PARTS
    ):
        return []

    public_class_nodes: list[ast.ClassDef] = [
        node
        for node in _non_docstring_body(module)
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]
    violations: list[Violation] = []

    if len(public_class_nodes) != 1:
        violations.append(
            Violation(
                code="SC024",
                path=file_path,
                line=1,
                message="client.py must define exactly one public top-level class",
            )
        )

    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)):
            continue
        violations.append(
            Violation(
                code="SC025",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message="client.py must contain only imports and top-level classes",
            )
        )

    return violations


def check_integration_adapter_helpers_module(
    *, repo_root: Path, file_path: Path
) -> list[Violation]:
    """Reject adapter-local helper modules that hide overrideable adapter behavior."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    integration_helper_module_part_count: int = 5
    if (
        file_path.name != HELPERS_MODULE_NAME
        or len(relative_parts) != integration_helper_module_part_count
        or relative_parts[:3] not in CLIENT_STYLE_ROOT_PARTS
    ):
        return []
    return [
        Violation(
            code="SC040",
            path=file_path,
            line=1,
            message=(
                "adapter helpers.py modules hide overrideable adapter behavior; "
                "put adapter-specific behavior on the adapter class"
            ),
        )
    ]


def check_adapter_contract_implementation_shortcuts(
    *,
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
    contract_class_names: frozenset[str] | None = None,
) -> list[Violation]:
    """Reject fake adapter contract implementations that hide BaseAdapter inheritance."""

    checked_class_names: frozenset[str] = contract_class_names or _adapter_contract_class_names(
        repo_root=repo_root,
        file_path=file_path,
        module=module,
    )
    if not checked_class_names:
        return []

    contract_methods: frozenset[str] = _strict_adapter_contract_method_names()
    violations: list[Violation] = []
    class_node: ast.ClassDef
    for class_node in (node for node in module.body if isinstance(node, ast.ClassDef)):
        if class_node.name not in checked_class_names:
            continue
        child: ast.stmt
        for child in class_node.body:
            if _is_base_adapter_method_alias(child):
                violations.append(
                    Violation(
                        code="SC037",
                        path=file_path,
                        line=getattr(child, "lineno", class_node.lineno),
                        message=(
                            "first-class adapter contract methods must copy implementations; "
                            "do not alias BaseAdapter methods"
                        ),
                    )
                )
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name not in contract_methods:
                    continue
                if any(_is_super_call(descendant) for descendant in ast.walk(child)):
                    violations.append(
                        Violation(
                            code="SC038",
                            path=file_path,
                            line=child.lineno,
                            message=(
                                "first-class adapter contract methods must copy implementations; "
                                "do not delegate to super()"
                            ),
                        )
                    )

    return violations


def check_no_sibling_package_imports(
    *,
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
) -> list[Violation]:
    """Reject direct imports from sibling subpackages instead of parent shared/."""

    current_package_parts: tuple[str, ...] = _subpackage_parts(
        repo_root=repo_root, file_path=file_path
    )
    nested_package_part_count: int = 3
    if len(current_package_parts) < nested_package_part_count:
        return []
    if current_package_parts[-1] == SHARED_PACKAGE_NAME:
        return []

    parent_package_parts: tuple[str, ...] = current_package_parts[:-1]
    current_subpackage_name: str = current_package_parts[-1]
    violations: list[Violation] = []

    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue

        imported_parts: tuple[str, ...] = tuple(node.module.split("."))
        if imported_parts[: len(parent_package_parts)] != parent_package_parts:
            continue
        if len(imported_parts) <= len(parent_package_parts):
            continue
        if _is_within_same_helpers_package(
            current_package_parts=current_package_parts, imported_parts=imported_parts
        ):
            continue

        sibling_name: str = imported_parts[len(parent_package_parts)]
        if (
            parent_package_parts[-1] == MAIN_PACKAGE_NAME
            and sibling_name in MAIN_SUPPORT_IMPORT_PACKAGE_NAMES
        ):
            continue
        if (
            sibling_name == HELPERS_PACKAGE_NAME
            and current_subpackage_name in SIBLING_HELPER_IMPORTER_PACKAGE_NAMES
        ):
            continue
        if sibling_name == CLASSES_PACKAGE_NAME and current_subpackage_name == HELPERS_PACKAGE_NAME:
            continue
        if sibling_name == CLASSES_PACKAGE_NAME and current_subpackage_name == MAIN_PACKAGE_NAME:
            continue
        if sibling_name in {SHARED_PACKAGE_NAME, current_subpackage_name}:
            continue
        if (
            current_subpackage_name == ENTRY_PACKAGE_NAME
            and parent_package_parts[-1] == MAIN_PACKAGE_NAME
            and imported_parts[-1] == MAIN_PACKAGE_NAME
        ):
            continue
        if len(imported_parts) == len(parent_package_parts) + 1:
            continue
        if _is_allowed_sibling_public_surface(
            parent_package_parts=parent_package_parts, imported_parts=imported_parts
        ):
            continue

        violations.append(
            Violation(
                code="SC011",
                path=file_path,
                line=node.lineno,
                message=(
                    "subpackage code must not import sibling package internals; "
                    f"promote shared code to {'.'.join(parent_package_parts + ('shared',))}"
                ),
            )
        )

    for node in ast.walk(module):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            imported_parts = tuple(alias.name.split("."))
            if imported_parts[: len(parent_package_parts)] != parent_package_parts:
                continue
            if len(imported_parts) <= len(parent_package_parts) + 1:
                continue
            if _is_within_same_helpers_package(
                current_package_parts=current_package_parts, imported_parts=imported_parts
            ):
                continue
            if _is_allowed_sibling_public_surface(
                parent_package_parts=parent_package_parts, imported_parts=imported_parts
            ):
                continue

            sibling_name = imported_parts[len(parent_package_parts)]
            if (
                parent_package_parts[-1] == MAIN_PACKAGE_NAME
                and sibling_name in MAIN_SUPPORT_IMPORT_PACKAGE_NAMES
            ):
                continue
            if (
                sibling_name == HELPERS_PACKAGE_NAME
                and current_subpackage_name in SIBLING_HELPER_IMPORTER_PACKAGE_NAMES
            ):
                continue
            if (
                sibling_name == CLASSES_PACKAGE_NAME
                and current_subpackage_name == HELPERS_PACKAGE_NAME
            ):
                continue
            if (
                sibling_name == CLASSES_PACKAGE_NAME
                and current_subpackage_name == MAIN_PACKAGE_NAME
            ):
                continue
            if sibling_name in {SHARED_PACKAGE_NAME, current_subpackage_name}:
                continue

            violations.append(
                Violation(
                    code="SC011",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "subpackage code must not import sibling package internals; "
                        f"promote shared code to {'.'.join(parent_package_parts + ('shared',))}"
                    ),
                )
            )

    return violations


def check_shared_package_imports(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject shared/ imports that reach into sibling package internals."""

    current_package_parts: tuple[str, ...] = _subpackage_parts(
        repo_root=repo_root, file_path=file_path
    )
    shared_package_part_count: int = 3
    if (
        len(current_package_parts) < shared_package_part_count
        or current_package_parts[-1] != SHARED_PACKAGE_NAME
    ):
        return []

    parent_package_parts: tuple[str, ...] = current_package_parts[:-1]
    violations: list[Violation] = []

    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_parts: tuple[str, ...] = tuple(node.module.split("."))
            if _is_forbidden_shared_import(
                parent_package_parts=parent_package_parts, imported_parts=imported_parts
            ):
                violations.append(
                    Violation(
                        code="SC013",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            "shared/ must not import sibling package internals; "
                            "shared code should stay dependency-neutral"
                        ),
                    )
                )

        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_parts = tuple(alias.name.split("."))
                if _is_forbidden_shared_import(
                    parent_package_parts=parent_package_parts, imported_parts=imported_parts
                ):
                    violations.append(
                        Violation(
                            code="SC013",
                            path=file_path,
                            line=node.lineno,
                            message=(
                                "shared/ must not import sibling package internals; "
                                "shared code should stay dependency-neutral"
                            ),
                        )
                    )

    return violations


def check_cross_package_internal_imports(
    *,
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
) -> list[Violation]:
    """Block imports that reach into another domain package's internal structure."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    runtime_domain_module_part_count: int = 4
    domain_and_subdomain_part_count: int = 3
    runtime_import_prefix_part_count: int = 3
    internal_module_import_part_count: int = 4
    if (
        len(relative_parts) < runtime_domain_module_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    top_level_domain: str = relative_parts[2]
    if top_level_domain in CROSS_PACKAGE_SOURCE_EXEMPT_DOMAIN_NAMES:
        return []

    current_domain_parts: tuple[str, ...] = relative_parts[2:]
    current_domain: str = current_domain_parts[0]
    current_subdomain: str | None = (
        current_domain_parts[1]
        if len(current_domain_parts) > domain_and_subdomain_part_count - 1
        else None
    )

    violations: list[Violation] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        imported_parts: tuple[str, ...] = tuple(node.module.split("."))
        if (
            len(imported_parts) < runtime_import_prefix_part_count
            or imported_parts[0] != SQLBUILD_PACKAGE_NAME
        ):
            continue

        imported_domain: str = imported_parts[1]
        if imported_domain == current_domain:
            if len(imported_parts) < internal_module_import_part_count:
                continue
            imported_subdomain: str = imported_parts[2]
            if current_subdomain is not None and imported_subdomain == current_subdomain:
                continue
            if imported_subdomain == SHARED_PACKAGE_NAME:
                continue
            if (
                len(imported_parts) >= internal_module_import_part_count
                and imported_parts[3] in CROSS_PACKAGE_PUBLIC_MODULE_NAMES
            ):
                continue
            if len(imported_parts) == runtime_import_prefix_part_count:
                continue
            if _has_deep_internal_segment(
                parts=imported_parts[3:], internal_segments=DEEP_INTERNAL_PACKAGE_NAMES
            ):
                violations.append(
                    Violation(
                        code="SC033",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            f"cross-package import reaches into internal structure of "
                            f"'{'.'.join(imported_parts[:3])}'; import from its public "
                            f"surface (classes, models, types, constants, exceptions, or a thin "
                            f"main/ entry module). If the code is helper logic rather than "
                            f"an entrypoint, move it to _helpers/ or, if broadly reused "
                            f"across domains, shared/"
                        ),
                    )
                )
            continue

        if imported_domain in CROSS_PACKAGE_TARGET_EXEMPT_DOMAIN_NAMES:
            continue

        if len(imported_parts) >= internal_module_import_part_count:
            target_module: str = imported_parts[2]
            if target_module in CROSS_PACKAGE_PUBLIC_MODULE_NAMES:
                continue
            if _has_deep_internal_segment(
                parts=imported_parts[2:], internal_segments=DEEP_INTERNAL_PACKAGE_NAMES
            ):
                violations.append(
                    Violation(
                        code="SC033",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            f"cross-package import reaches into internal structure of "
                            f"'{'.'.join(imported_parts[:2])}'; import from its public "
                            f"surface (classes, models, types, constants, exceptions, or a thin "
                            f"main/ entry module). If the code is helper logic rather than "
                            f"an entrypoint, move it to _helpers/ or, if broadly reused "
                            f"across domains, shared/"
                        ),
                    )
                )

    return violations


def check_entry_module_shape(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Enforce entry modules as focused single-entry surfaces."""

    if not _is_entry_module(file_path):
        return []
    if _is_orchestration_integration_public_entry(file_path):
        return []

    public_function_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        node
        for node in _non_docstring_body(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    private_function_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        node
        for node in _non_docstring_body(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_")
    ]
    violations: list[Violation] = []

    if len(public_function_nodes) != 1:
        violations.append(
            Violation(
                code="SC019",
                path=file_path,
                line=1,
                message=("entry modules must define exactly one public top-level function"),
            )
        )

    private_entry_helper_limit: int = 2
    if len(private_function_nodes) > private_entry_helper_limit:
        violations.append(
            Violation(
                code="SC026",
                path=file_path,
                line=private_function_nodes[2].lineno,
                message=(
                    "entry modules must define at most two private top-level functions; "
                    "extract additional behavior to sibling modules under main/ or _helpers/ "
                    "support code"
                ),
            )
        )

    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        violations.append(
            Violation(
                code="SC020",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message="entry modules must contain only imports and top-level functions",
            )
        )

    return violations
