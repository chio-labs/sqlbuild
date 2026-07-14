"""Rule implementations for structure convention checks."""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterator
from pathlib import Path

from scripts.structure._helpers.rule_ast import (
    _assigned_local_names,
    _call_base_name,
    _call_display_name,
    _call_is_inside_loop,
    _call_name,
    _compare_mentions_dbt_ref_kind,
    _dataclass_is_frozen,
    _discarded_call_is_allowed,
    _distinct_callee_names,
    _docstring_bearing_nodes,
    _function_parameter_names,
    _handler_body_is_single_swallow,
    _is_adapter_implementation_file,
    _is_all_assignment,
    _is_allowed_model_class,
    _is_allowed_reexport_surface,
    _is_allowed_type_class,
    _is_bare_exception_handler,
    _is_compiler_or_executor_helper_module,
    _is_dataclass_class,
    _is_direct_child_of_main_package,
    _is_main_package_module,
    _is_orchestration_integration_public_init,
    _is_orchestration_integration_public_module,
    _is_pure_reexport_module,
    _is_runtime_file,
    _is_runtime_source_file,
    _is_sc045_term_allowed,
    _is_selector_plus_string_method_call,
    _is_type_checking_import_block,
    _is_within_main_package,
    _is_within_role_package,
    _line_allows_parameter_mutation,
    _main_support_folder_violation,
    _metadata_bearing_helper_names,
    _metadata_call_label,
    _non_docstring_body,
    _parameter_mutated_by_node,
    _path_is_allowed,
    _raise_uses_raw_builtin,
    _role_package_layout_dir,
    _role_package_layout_violations,
    _statement_is_multiline_docstring,
    _top_level_function_nodes,
    is_docstring_only_module,
)
from scripts.structure.constants import (
    ADAPTER_ROOT_PARTS,
    BANNED_GENERIC_FILENAMES,
    CLIENT_MODULE_NAME,
    CLIENT_STYLE_ROOT_PARTS,
    CONSTANTS_MODULE_NAME,
    DBT_INTEGRATION_PATH_MARKER,
    DEV_TOOLING_FILE_PREFIXES,
    DEV_TOOLING_SEGMENTS,
    DIRECT_TOP_LEVEL_ROLE_MODULE_NAMES,
    ENTRY_MODULE_EXCLUDED_NAMES,
    GRAPH_KEY_CLASS_NAMES,
    HELPERS_MODULE_NAME,
    HELPERS_PACKAGE_NAME,
    INIT_MODULE_NAME,
    INSERT_SQL_PREFIX,
    INTEGRATIONS_ROOT_PARTS,
    LOAD_PROJECT_MACROS_NAME,
    MAIN_MODULE_NAME,
    MAIN_PACKAGE_NAME,
    MODELS_MODULE_NAME,
    MODELS_PACKAGE_NAME,
    NESTED_ALLOWED_CHILD_PACKAGE_NAMES,
    NESTED_RUNTIME_ROLE_MODULE_NAMES,
    PLANNER_PATH_MARKER,
    PROVIDER_CLASS_NAME,
    PROVIDER_MODULE_PARTS,
    PYTHON_FILE_SUFFIX,
    RAW_COLOR_CAPABILITY_MODULE_NAME,
    ROLE_BOUNDARY_NAMES,
    RUNTIME_ROOT_PARTS,
    SHARED_PACKAGE_NAME,
    SOURCE_FRESHNESS_TEXT_MARKERS,
    SQLBUILD_SOURCE_PATH_MARKER,
    SUPPORT_PACKAGE_NAMES,
    SUPPORTED_TOP_LEVEL_DIRECT_MODULE_NAMES,
    TOP_LEVEL_EXEMPT_DOMAIN_NAMES,
    TYPES_MODULE_NAME,
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


def parse_python_module(file_path: Path) -> ast.Module:
    """Parse a Python file into an AST module."""

    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def check_no_relative_imports(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject relative imports in runtime and script code."""

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            violations.append(
                Violation(
                    code="SC001",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "runtime and script modules must use absolute imports, not relative imports"
                    ),
                )
            )
    return violations


def check_target_reuse_terminology(file_path: Path) -> list[Violation]:
    """Reject ambiguous source/target wording in reuse implementation modules."""

    path_text: str = file_path.as_posix()
    if path_text.endswith(("/module_rules.py", "/package_rules.py", "/rule_ast.py")):
        return []
    check_scoped_terms: bool = any(marker in path_text for marker in _TARGET_REUSE_PATH_MARKERS)

    violations: list[Violation] = []
    lines: list[str] = file_path.read_text(encoding="utf-8").splitlines()
    line_number: int
    line: str
    for line_number, line in enumerate(lines, start=1):
        term: str
        terms: tuple[str, ...] = _GLOBAL_REUSE_FORBIDDEN_TERMS
        if check_scoped_terms:
            terms = (*terms, *_TARGET_REUSE_FORBIDDEN_TERMS)
        for term in terms:
            if term in line and not _is_sc045_term_allowed(path_text=path_text, term=term):
                violations.append(
                    Violation(
                        code="SC045",
                        path=file_path,
                        line=line_number,
                        message=(
                            f"clone/reuse code must not use ambiguous term '{term}'; "
                            "use origin/destination/reuse_from terminology because 'source' "
                            "means SQLBuild source nodes. If this is real SQLBuild source logic, "
                            "add a narrow path exception for this term in SC045."
                        ),
                    )
                )
    return violations


def check_no_raw_color_helper_imports(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject direct imports from the presentation color capability implementation."""

    if file_path.as_posix().endswith("src/sqlbuild/presentation/main/supports_color.py"):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == RAW_COLOR_CAPABILITY_MODULE_NAME:
            violations.append(
                Violation(
                    code="SC041",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "runtime modules must import supports_color through "
                        "sqlbuild.presentation.main.supports_color"
                    ),
                )
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == RAW_COLOR_CAPABILITY_MODULE_NAME:
                    violations.append(
                        Violation(
                            code="SC041",
                            path=file_path,
                            line=node.lineno,
                            message=(
                                "runtime modules must not import presentation color capability "
                                "implementation directly; use presentation/main"
                            ),
                        )
                    )
    return violations


def check_no_singular_source_freshness_writer(
    *, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject per-record source freshness writer imports and calls."""

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            alias: ast.alias
            for alias in node.names:
                if alias.name == _SOURCE_FRESHNESS_SINGULAR_WRITER_NAME:
                    violations.append(
                        Violation(
                            code="SC057",
                            path=file_path,
                            line=node.lineno,
                            message=(
                                "source freshness state writes must use "
                                "write_source_freshness_records() batch writes"
                            ),
                        )
                    )
        if (
            isinstance(node, ast.Call)
            and _call_name(node) == _SOURCE_FRESHNESS_SINGULAR_WRITER_NAME
        ):
            violations.append(
                Violation(
                    code="SC057",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "source freshness state writes must use "
                        "write_source_freshness_records() batch writes"
                    ),
                )
            )
    return violations


def check_no_source_freshness_insert_sql_outside_adapters(file_path: Path) -> list[Violation]:
    """Reject source freshness INSERT SQL outside adapter-owned renderers."""

    path_text: str = file_path.as_posix()
    if any(marker in path_text for marker in _SOURCE_FRESHNESS_INSERT_ALLOWED_MARKERS):
        return []
    contents: str = file_path.read_text(encoding="utf-8")
    if all(marker not in contents for marker in SOURCE_FRESHNESS_TEXT_MARKERS):
        return []
    violations: list[Violation] = []
    line_number: int
    line: str
    for line_number, line in enumerate(contents.splitlines(), start=1):
        if INSERT_SQL_PREFIX in line:
            violations.append(
                Violation(
                    code="SC058",
                    path=file_path,
                    line=line_number,
                    message=(
                        "source freshness INSERT SQL must be rendered by adapter methods, "
                        "not runtime/compiler helpers"
                    ),
                )
            )
    return violations


def check_no_internal_reexport_modules(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject internal modules that only re-export imports from another module."""

    if not _is_runtime_file(repo_root=repo_root, file_path=file_path):
        return []
    if _is_allowed_reexport_surface(repo_root=repo_root, file_path=file_path):
        return []
    if not _is_pure_reexport_module(module):
        return []
    return [
        Violation(
            code="SC046",
            path=file_path,
            line=1,
            message=(
                "runtime modules must not be pure re-export shims; import from the "
                "implementation module directly or define a real public API surface"
            ),
        )
    ]


def check_no_internal_helper_exports(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject __all__ export surfaces inside internal helper packages."""

    if not _is_runtime_file(repo_root=repo_root, file_path=file_path):
        return []
    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if HELPERS_PACKAGE_NAME not in relative_parts:
        return []
    integration_module_path_part_count: int = 4
    if (
        len(relative_parts) >= integration_module_path_part_count
        and relative_parts[:3] == INTEGRATIONS_ROOT_PARTS
    ):
        return []

    violations: list[Violation] = []
    for node in module.body:
        if _is_all_assignment(node):
            violations.append(
                Violation(
                    code="SC047",
                    path=file_path,
                    line=getattr(node, "lineno", 1),
                    message=(
                        "internal helper modules must not define __all__; expose public APIs "
                        "from an approved public surface instead"
                    ),
                )
            )
    return violations


def check_source_file_line_count(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject oversized runtime source files outside explicit backend allowlists."""

    relative_path: Path = file_path.resolve().relative_to(repo_root.resolve())
    relative_text: str = relative_path.as_posix()
    if not relative_text.startswith("src/sqlbuild/"):
        return []
    if any(relative_path.match(pattern) for pattern in _MAX_SOURCE_LINE_ALLOWED_PATTERNS):
        return []

    line_count: int = len(file_path.read_text(encoding="utf-8").splitlines())
    if line_count <= _MAX_SOURCE_FILE_LINES:
        return []

    return [
        Violation(
            code="SC048",
            path=file_path,
            line=None,
            message=(
                f"source file exceeds {_MAX_SOURCE_FILE_LINES} lines ({line_count}); "
                "split by concern unless this path is explicitly allowlisted as an "
                "adapter/client or virtual-state backend boundary"
            ),
        )
    ]


def check_helpers_package_layout(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Enforce consistent flat-or-subfolder helper package layout."""

    package_dir: Path | None = _role_package_layout_dir(
        file_path=file_path, package_name="_helpers"
    )
    if package_dir is None:
        return []

    return _role_package_layout_violations(
        package_dir=package_dir,
        file_path=file_path,
        package_name="_helpers",
        mixed_code="SC049",
        too_many_code="SC050",
        module_label="helper",
        max_flat_modules=_MAX_HELPER_FLAT_MODULES,
        ignored_subfolder_names=frozenset(),
    )


def check_main_package_layout(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Enforce consistent flat-or-subfolder main package layout."""

    support_violation: Violation | None = _main_support_folder_violation(
        repo_root=repo_root,
        file_path=file_path,
    )
    package_dir: Path | None = _role_package_layout_dir(file_path=file_path, package_name="main")
    if package_dir is None:
        return [support_violation] if support_violation is not None else []

    violations: list[Violation] = _role_package_layout_violations(
        package_dir=package_dir,
        file_path=file_path,
        package_name="main",
        mixed_code="SC059",
        too_many_code="SC060",
        module_label="entry",
        max_flat_modules=_MAX_MAIN_FLAT_MODULES,
        ignored_subfolder_names=_MAIN_SUPPORT_FOLDER_NAMES,
    )
    if support_violation is not None:
        violations.append(support_violation)
    return violations


def check_banned_generic_filename(file_path: Path) -> list[Violation]:
    """Reject vague generic module names in runtime and script code."""

    if file_path.name not in BANNED_GENERIC_FILENAMES:
        return []

    return [
        Violation(
            code="SC003",
            path=file_path,
            line=None,
            message=(
                f"uses banned generic filename '{file_path.name}'; choose a domain-specific name"
            ),
        )
    ]


def check_top_level_domain_role_placement(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject direct role files or role directories under top-level runtime domains."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    top_level_domain_child_part_count: int = 4
    nested_domain_child_part_count: int = 5
    if (
        len(relative_parts) < top_level_domain_child_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    if relative_parts[2] in TOP_LEVEL_EXEMPT_DOMAIN_NAMES:
        return []

    direct_child_name: str = relative_parts[3]
    if (
        len(relative_parts) == top_level_domain_child_part_count
        and direct_child_name in DIRECT_TOP_LEVEL_ROLE_MODULE_NAMES
        and (relative_parts[2], direct_child_name) not in _TOP_LEVEL_ROLE_FILE_ALLOWED_PAIRS
    ):
        return [
            Violation(
                code="SC017",
                path=file_path,
                line=None,
                message=(
                    "top-level runtime domains must not contain direct role files; "
                    "move them into a subpackage or shared/"
                ),
            )
        ]

    if (
        len(relative_parts) >= nested_domain_child_part_count
        and direct_child_name in SUPPORT_PACKAGE_NAMES
        and (relative_parts[2], direct_child_name) not in _TOP_LEVEL_SUPPORT_PACKAGE_ALLOWED_PAIRS
        and file_path.name == INIT_MODULE_NAME
    ):
        return [
            Violation(
                code="SC017",
                path=file_path,
                line=None,
                message=(
                    "top-level runtime domains must not contain direct _helpers/ or classes/; "
                    "move them into a subpackage or shared/"
                ),
            )
        ]

    return []


def check_top_level_domain_direct_modules(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject direct modules under top-level runtime domains except role files."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    top_level_domain_module_part_count: int = 4
    if (
        len(relative_parts) != top_level_domain_module_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    if file_path.name in SUPPORTED_TOP_LEVEL_DIRECT_MODULE_NAMES:
        return []

    return [
        Violation(
            code="SC018",
            path=file_path,
            line=None,
            message=(
                "top-level runtime domains must contain subpackages, not direct modules; "
                "keep direct files limited to role-oriented files like models.py or types.py"
            ),
        )
    ]


def check_public_provider_module_shape(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Keep the public sqlbuild.providers module intentionally tiny."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if relative_parts != PROVIDER_MODULE_PARTS:
        return []

    violations: list[Violation] = []
    public_class_names: list[str] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ClassDef):
            if node.name == PROVIDER_CLASS_NAME:
                public_class_names.append(node.name)
                continue
            violations.append(
                Violation(
                    code="SC042",
                    path=file_path,
                    line=node.lineno,
                    message="src/sqlbuild/providers.py may only define the public Provider class",
                )
            )
            continue
        violations.append(
            Violation(
                code="SC042",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message="src/sqlbuild/providers.py may contain only imports and class Provider",
            )
        )

    if public_class_names != [PROVIDER_CLASS_NAME]:
        violations.append(
            Violation(
                code="SC042",
                path=file_path,
                line=1,
                message="src/sqlbuild/providers.py must define exactly one public Provider class",
            )
        )
    return violations


def check_nested_runtime_package_direct_modules(
    *, repo_root: Path, file_path: Path
) -> list[Violation]:
    """Reject ad hoc direct modules in nested runtime packages outside _helpers/."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    nested_runtime_module_part_count: int = 5
    if (
        len(relative_parts) < nested_runtime_module_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    if _is_orchestration_integration_public_module(relative_parts):
        return []
    if file_path.name == MAIN_MODULE_NAME and (
        relative_parts[:3] in CLIENT_STYLE_ROOT_PARTS or SHARED_PACKAGE_NAME in relative_parts[2:-1]
    ):
        return []
    if _is_direct_child_of_main_package(relative_parts):
        return []
    if _is_within_main_package(relative_parts):
        return []
    if any(part in ROLE_BOUNDARY_NAMES for part in relative_parts[2:-1]):
        return []
    if file_path.name in NESTED_RUNTIME_ROLE_MODULE_NAMES:
        return []
    if (
        len(relative_parts) >= nested_runtime_module_part_count
        and relative_parts[:3] in CLIENT_STYLE_ROOT_PARTS
        and file_path.name == CLIENT_MODULE_NAME
    ):
        return []
    if (
        len(relative_parts) >= nested_runtime_module_part_count
        and relative_parts[:3] == ADAPTER_ROOT_PARTS
        and file_path.name.endswith(PYTHON_FILE_SUFFIX)
        and file_path.name not in ENTRY_MODULE_EXCLUDED_NAMES
    ):
        return []

    return [
        Violation(
            code="SC027",
            path=file_path,
            line=None,
            message=(
                "nested runtime packages must keep direct files to role-oriented modules; "
                "move additional support code under _helpers/"
            ),
        )
    ]


def check_nested_runtime_package_direct_subpackages(
    *, repo_root: Path, file_path: Path
) -> list[Violation]:
    """Reject arbitrary direct child packages under nested runtime packages."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    nested_runtime_subpackage_part_count: int = 6
    top_level_package_part_count: int = 3
    if (
        len(relative_parts) < nested_runtime_subpackage_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    if file_path.name != INIT_MODULE_NAME:
        return []

    parent_package_parts: tuple[str, ...] = relative_parts[:-2]
    if len(parent_package_parts) <= top_level_package_part_count:
        return []

    parent_package_name: str = parent_package_parts[-1]
    direct_child_name: str = relative_parts[-2]
    if _is_within_main_package(relative_parts):
        return []
    if parent_package_name in ROLE_BOUNDARY_NAMES:
        return []
    if direct_child_name in NESTED_ALLOWED_CHILD_PACKAGE_NAMES:
        return []
    return [
        Violation(
            code="SC030",
            path=file_path,
            line=1,
            message=(
                "nested runtime packages must use direct subpackages only for explicit "
                "support boundaries like _helpers/, shared/, classes/, or main/; move "
                "feature buckets under _helpers/ or flatten them into role files"
            ),
        )
    ]


def check_main_entry_name_collisions(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject duplicate flat-module and package entry names directly under main/."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    nested_main_module_part_count: int = 6
    deeply_nested_main_module_part_count: int = 7
    if (
        len(relative_parts) < nested_main_module_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []
    if (
        file_path.parent.name != MAIN_PACKAGE_NAME
        or file_path.suffix != PYTHON_FILE_SUFFIX
        or file_path.name == INIT_MODULE_NAME
    ):
        return []
    if (
        len(relative_parts) < deeply_nested_main_module_part_count
        or relative_parts[-3] != MAIN_PACKAGE_NAME
    ):
        return []
    if not file_path.with_suffix("").is_dir():
        return []

    return [
        Violation(
            code="SC029",
            path=file_path,
            line=None,
            message=(
                "main/ must not define both a flat module and a package with the same entry "
                "name; choose one entry surface"
            ),
        )
    ]


def check_dev_tooling_location(*, repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject obvious dev-tooling modules under src/sqlbuild."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    runtime_package_prefix_part_count: int = 2
    if (
        len(relative_parts) < runtime_package_prefix_part_count
        or relative_parts[:2] != RUNTIME_ROOT_PARTS
    ):
        return []

    file_stem: str = file_path.stem
    if file_stem.startswith(DEV_TOOLING_FILE_PREFIXES):
        return [
            Violation(
                code="SC002",
                path=file_path,
                line=None,
                message="dev-only tooling must live under scripts/, not src/sqlbuild",
            )
        ]

    if any(part in DEV_TOOLING_SEGMENTS for part in relative_parts[2:-1]):
        return [
            Violation(
                code="SC002",
                path=file_path,
                line=None,
                message="dev-only tooling must live under scripts/, not src/sqlbuild",
            )
        ]

    return []


def check_helpers_module_name(file_path: Path) -> list[Violation]:
    """Reject helpers.py in favor of a _helpers/ package."""

    if file_path.name != HELPERS_MODULE_NAME:
        return []

    return [
        Violation(
            code="SC004",
            path=file_path,
            line=None,
            message="use a _helpers/ package instead of helpers.py",
        )
    ]


def check_init_module(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate __init__.py contents."""

    if file_path.name != INIT_MODULE_NAME:
        return []
    if _is_orchestration_integration_public_init(file_path):
        return []

    if is_docstring_only_module(module):
        return []

    return [
        Violation(
            code="SC006",
            path=file_path,
            line=1,
            message="__init__.py must be empty or docstring-only",
        )
    ]


def check_types_module(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate types.py contents."""

    if file_path.name != TYPES_MODULE_NAME:
        return []

    violations: list[Violation] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.TypeAlias)):
            continue
        if _is_type_checking_import_block(node):
            continue
        if isinstance(node, ast.ClassDef) and _is_allowed_type_class(node):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.append(
                Violation(
                    code="SC007",
                    path=file_path,
                    line=node.lineno,
                    message="types.py must not define runtime functions",
                )
            )
            continue
        violations.append(
            Violation(
                code="SC007",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message=(
                    "types.py must contain only type-layer declarations such as TypeAlias, "
                    "TypedDict, Protocol, NamedTuple, or Enum"
                ),
            )
        )
    return violations


def check_models_module(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate models.py contents."""

    if file_path.name != MODELS_MODULE_NAME:
        return []

    violations: list[Violation] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ClassDef) and _is_allowed_model_class(node):
            if _is_dataclass_class(node) and not _dataclass_is_frozen(node):
                violations.append(
                    Violation(
                        code="SC068",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            "models.py dataclasses must set frozen=True; result models are "
                            "shared across phases and must be immutable"
                        ),
                    )
                )
            continue
        violations.append(
            Violation(
                code="SC008",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message=(
                    "models.py must contain only structured runtime models such as dataclasses "
                    "or pydantic models"
                ),
            )
        )
    return violations


def check_main_public_function_shape(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Cap main/ top-level functions so they stay phase-shaped orchestrators."""

    if not _is_main_package_module(file_path):
        return []

    violations: list[Violation] = []
    function_node: ast.FunctionDef | ast.AsyncFunctionDef
    for function_node in _top_level_function_nodes(module):
        function_label: str = (
            "private function" if function_node.name.startswith("_") else "public function"
        )
        statement_count: int = (
            sum(1 for node in ast.walk(function_node) if isinstance(node, ast.stmt)) - 1
        )
        if statement_count > _MAX_MAIN_PUBLIC_FUNCTION_STATEMENTS:
            violations.append(
                Violation(
                    code="SC063",
                    path=file_path,
                    line=function_node.lineno,
                    message=(
                        f"{function_label} '{function_node.name}' has {statement_count} "
                        "statements (main/ limit: 40). "
                        f"{_MAIN_PHASE_REMEDIATION_MESSAGE}"
                    ),
                )
            )

        distinct_calls: int = len(_distinct_callee_names(function_node))
        if distinct_calls > _MAX_MAIN_PUBLIC_FUNCTION_DISTINCT_CALLS:
            violations.append(
                Violation(
                    code="SC064",
                    path=file_path,
                    line=function_node.lineno,
                    message=(
                        f"{function_label} '{function_node.name}' calls {distinct_calls} "
                        "distinct functions (main/ limit: 20). "
                        f"{_MAIN_PHASE_REMEDIATION_MESSAGE}"
                    ),
                )
            )

        local_count: int = len(_assigned_local_names(function_node))
        if local_count > _MAX_MAIN_PUBLIC_FUNCTION_LOCALS:
            violations.append(
                Violation(
                    code="SC065",
                    path=file_path,
                    line=function_node.lineno,
                    message=(
                        f"{function_label} '{function_node.name}' juggles {local_count} "
                        "local variables (main/ limit: 20). This usually means multiple "
                        "phases' intermediate state is interleaved; each extracted phase "
                        "should own its intermediates and return one result model."
                    ),
                )
            )
    return violations


def check_main_discarded_call_results(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Require main/ orchestrators to consume phase call results."""

    if not _is_main_package_module(file_path):
        return []

    violations: list[Violation] = []
    function_node: ast.FunctionDef | ast.AsyncFunctionDef
    for function_node in _top_level_function_nodes(module):
        node: ast.AST
        for node in ast.walk(function_node):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            if _discarded_call_is_allowed(node.value):
                continue
            violations.append(
                Violation(
                    code="SC066",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        f"result of '{_call_display_name(node.value)}' is discarded in "
                        f"main/ orchestrator '{function_node.name}'. Phases must return "
                        "their effect as a value (assign to a typed local or return it). "
                        "Bare calls are reserved for validators (validate_*/enforce_*/"
                        "check_*), callbacks and progress (on_*/report_*), diagnostics "
                        "(log*/print), and writers (write_*); discard a genuine void "
                        "effect explicitly with '_ = ...'. Do not communicate between "
                        "phases by mutation."
                    ),
                )
            )
    return violations


def check_no_parameter_mutation_in_phase_helpers(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject hidden dataflow from mutating function parameters in phase helpers."""

    if not _is_compiler_or_executor_helper_module(repo_root=repo_root, file_path=file_path):
        return []

    source_lines: list[str] = file_path.read_text(encoding="utf-8").splitlines()
    violations: list[Violation] = []
    function_node: ast.FunctionDef | ast.AsyncFunctionDef
    for function_node in (
        node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        parameter_names: frozenset[str] = _function_parameter_names(function_node)
        node: ast.AST
        for node in ast.walk(function_node):
            mutated_name: str | None = _parameter_mutated_by_node(
                node=node,
                parameter_names=parameter_names,
            )
            if mutated_name is None:
                continue
            line_number: int = getattr(node, "lineno", function_node.lineno)
            if _line_allows_parameter_mutation(source_lines=source_lines, line_number=line_number):
                continue
            violations.append(
                Violation(
                    code="SC067",
                    path=file_path,
                    line=line_number,
                    message=(
                        f"'{mutated_name}' is a parameter and is mutated here. Helpers should "
                        "accept inputs and return results; mutating arguments hides dataflow "
                        "from callers. Return a new/updated value instead, or mark a deliberate "
                        "builder with '# sc: allow-param-mutation'."
                    ),
                )
            )
    return violations


def check_constants_module(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate constants.py contents."""

    if file_path.name != CONSTANTS_MODULE_NAME:
        return []

    violations: list[Violation] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)):
            continue
        violations.append(
            Violation(
                code="SC009",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message=(
                    "constants.py must contain only constant assignments and supporting imports"
                ),
            )
        )
    return violations


def check_model_declarations_outside_models(
    *, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject model declarations outside models.py."""

    if file_path.name == MODELS_MODULE_NAME or _is_within_role_package(
        file_path=file_path, role_directory_name=MODELS_PACKAGE_NAME
    ):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and _is_allowed_model_class(node):
            violations.append(
                Violation(
                    code="SC014",
                    path=file_path,
                    line=node.lineno,
                    message="structured runtime models must be defined in models.py",
                )
            )
    return violations


def check_no_raw_runtime_diagnostics(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject raw built-in raises and asserts in production runtime code."""

    if not _is_runtime_source_file(file_path):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Raise) and _raise_uses_raw_builtin(node):
            violations.append(
                Violation(
                    code="SC035",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "production code must raise a structured SQLBuild error instead of "
                        "a raw built-in exception"
                    ),
                )
            )
        if isinstance(node, ast.Assert):
            violations.append(
                Violation(
                    code="SC036",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "production code must not use assert for runtime invariants; "
                        "raise a structured SQLBuild error"
                    ),
                )
            )
    return violations


def check_no_swallowed_exception_probes(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject broad exception handlers that silently answer existence probes."""

    if not _is_runtime_source_file(file_path):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_bare_exception_handler(node):
            continue
        if not _handler_body_is_single_swallow(node.body):
            continue
        violations.append(
            Violation(
                code="SC044",
                path=file_path,
                line=node.lineno,
                message=(
                    "runtime code must not swallow broad exceptions as existence probe "
                    "answers; use adapter metadata checks or log best-effort fallbacks"
                ),
            )
        )
    return violations


def check_no_metadata_calls_in_loops(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject per-iteration warehouse metadata calls that scale as N+1 queries."""

    if not _is_runtime_source_file(file_path):
        return []
    if _is_adapter_implementation_file(file_path):
        return []
    path_text: str = file_path.as_posix()
    if any(marker in path_text for marker in _SC051_BATCHED_REASON_BY_PATH):
        return []

    parents: dict[ast.AST, ast.AST] = {}
    parent: ast.AST
    for parent in ast.walk(module):
        child: ast.AST
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    bearing_method_names, bearing_function_names = _metadata_bearing_helper_names(
        module=module, parents=parents
    )

    violations: list[Violation] = []
    node: ast.AST
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        label: str | None = _metadata_call_label(
            node=node,
            bearing_method_names=bearing_method_names,
            bearing_function_names=bearing_function_names,
        )
        if label is None or not _call_is_inside_loop(node=node, parents=parents):
            continue
        violations.append(
            Violation(
                code="SC051",
                path=file_path,
                line=node.lineno,
                message=(
                    f"'{label}' reaches a warehouse metadata call and runs inside a loop, which "
                    "scales as N+1 queries; gather relations once with build_relation_lookup "
                    "(or a planner WarehouseSnapshot) before the loop. If the loop already "
                    "batches one query per database or runs per microbatch window, add a "
                    "narrow path exception in SC051 with a reason."
                ),
            )
        )
    return violations


def check_no_ad_hoc_dbt_ref_scans(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject direct dbt ref-kind scans outside the centralized resolver."""

    path_text: str = file_path.as_posix()
    if DBT_INTEGRATION_PATH_MARKER not in path_text:
        return []
    if _path_is_allowed(path_text=path_text, allowed_paths=_SC052_DBT_REF_SCAN_ALLOWED_PATHS):
        return []

    violations: list[Violation] = []
    node: ast.AST
    for node in ast.walk(module):
        if not isinstance(node, ast.Compare):
            continue
        if _compare_mentions_dbt_ref_kind(node):
            violations.append(
                Violation(
                    code="SC052",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "dbt integration code must resolve SQLBuild __dbt_ref references through "
                        "_helpers/manifest/sqlbuild_refs.py instead of scanning ref_kind locally"
                    ),
                )
            )
    return violations


def check_no_ad_hoc_dbt_graph_projection(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject direct planner graph-key construction in dbt code outside projection helpers."""

    path_text: str = file_path.as_posix()
    if DBT_INTEGRATION_PATH_MARKER not in path_text:
        return []
    if path_text.endswith("src/sqlbuild/integrations/dbt/_helpers/planning/graph_projection.py"):
        return []

    violations: list[Violation] = []
    node: ast.AST
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        called_name: str | None = _call_base_name(node)
        if called_name not in GRAPH_KEY_CLASS_NAMES:
            continue
        violations.append(
            Violation(
                code="SC053",
                path=file_path,
                line=node.lineno,
                message=(
                    "dbt code must construct neutral planner graph keys through "
                    "_helpers/planning/graph_projection.py so model/seed/source mapping "
                    "cannot drift"
                ),
            )
        )
    return violations


def check_no_ad_hoc_selector_plus_parsing(
    *, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject local +selector marker parsing in planner and dbt selection code."""

    path_text: str = file_path.as_posix()
    if not (DBT_INTEGRATION_PATH_MARKER in path_text or PLANNER_PATH_MARKER in path_text):
        return []
    if _path_is_allowed(
        path_text=path_text,
        allowed_paths=_SC054_SELECTOR_PLUS_PARSE_ALLOWED_PATHS,
    ):
        return []

    violations: list[Violation] = []
    node: ast.AST
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not _is_selector_plus_string_method_call(node):
            continue
        violations.append(
            Violation(
                code="SC054",
                path=file_path,
                line=node.lineno,
                message=(
                    "planner and dbt selector code must parse + markers with "
                    "sqlbuild.compiler.planner.main.planning.selector_expansion.split_selector_expansion"
                ),
            )
        )
    return violations


def check_single_project_macro_load_site(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject load_project_macros usage outside the single compile-input load site."""

    path_text: str = file_path.as_posix()
    if SQLBUILD_SOURCE_PATH_MARKER not in path_text:
        return []
    if _path_is_allowed(path_text=path_text, allowed_paths=_SC062_MACRO_LOAD_ALLOWED_PATHS):
        return []

    violations: list[Violation] = []
    node: ast.AST
    for node in ast.walk(module):
        line: int | None = None
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == LOAD_PROJECT_MACROS_NAME for alias in node.names or []
        ):
            line = node.lineno
        if isinstance(node, ast.Call) and _call_base_name(node) == LOAD_PROJECT_MACROS_NAME:
            line = node.lineno
        if line is None:
            continue
        violations.append(
            Violation(
                code="SC062",
                path=file_path,
                line=line,
                message=(
                    "user macros must be loaded once in build_compile_inputs and passed "
                    "down as loaded_macros; do not call load_project_macros elsewhere"
                ),
            )
        )
    return violations


def check_single_line_docstrings(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject new multiline docstrings in runtime and script code."""

    violations: list[Violation] = []
    node: ast.AST
    for node in _docstring_bearing_nodes(module):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first_statement: ast.stmt = node.body[0]
        if not _statement_is_multiline_docstring(first_statement):
            continue
        violations.append(
            Violation(
                code="SC055",
                path=file_path,
                line=first_statement.lineno,
                message=(
                    "docstrings must be a single line; move extended explanation into docs or tests"
                ),
            )
        )
    return violations


def check_no_standalone_comments(file_path: Path) -> list[Violation]:
    """Reject standalone explanatory comments outside narrow legacy/tooling exceptions."""

    violations: list[Violation] = []
    source: str = file_path.read_text(encoding="utf-8")
    token: tokenize.TokenInfo
    try:
        tokens: Iterator[tokenize.TokenInfo] = tokenize.generate_tokens(
            io.StringIO(source).readline
        )
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            comment: str = token.string.strip()
            if comment.startswith(_SC056_COMMENT_ALLOWED_PREFIXES):
                continue
            violations.append(
                Violation(
                    code="SC056",
                    path=file_path,
                    line=token.start[0],
                    message=(
                        "standalone comments are not allowed in runtime/script code; prefer clear "
                        "names or a single-line docstring, and use docs/tests for longer context"
                    ),
                )
            )
    except tokenize.TokenError:
        return []
    return violations
