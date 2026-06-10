"""Rule implementations for structure convention checks."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from scripts.structure.structure_conventions.constants import (
    BANNED_GENERIC_FILENAMES,
    DEV_TOOLING_FILE_PREFIXES,
    DEV_TOOLING_SEGMENTS,
    MODEL_CLASS_BASE_NAMES,
    RAW_BUILTIN_RAISE_NAMES,
    TYPE_CLASS_BASE_NAMES,
)
from scripts.structure.structure_conventions.models import Violation

_TARGET_REUSE_PATH_MARKERS: tuple[str, ...] = (
    "standard_reuse",
    "reuse.py",
)
_TARGET_REUSE_FORBIDDEN_TERMS: tuple[str, ...] = (
    "source_relation",
    "source_cursor",
    "source_fingerprint",
    "source_version",
    "target_relation",
    "target_cursor",
    "REUSE_RELATION",
    "reuse_relation",
)


def parse_python_module(file_path: Path) -> ast.Module:
    """Parse a Python file into an AST module."""

    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def check_no_relative_imports(file_path: Path, module: ast.Module) -> list[Violation]:
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
    """Reject ambiguous source/target wording in target-reuse implementation modules."""

    path_text: str = file_path.as_posix()
    if not any(marker in path_text for marker in _TARGET_REUSE_PATH_MARKERS):
        return []

    violations: list[Violation] = []
    lines: list[str] = file_path.read_text(encoding="utf-8").splitlines()
    line_number: int
    line: str
    for line_number, line in enumerate(lines, start=1):
        term: str
        for term in _TARGET_REUSE_FORBIDDEN_TERMS:
            if term in line:
                violations.append(
                    Violation(
                        code="SC045",
                        path=file_path,
                        line=line_number,
                        message=(
                            f"target-reuse modules must not use ambiguous term '{term}'; "
                            "use origin/destination/reuse_from terminology unless this is real "
                            "SQLBuild source logic"
                        ),
                    )
                )
    return violations


def check_no_raw_color_helper_imports(file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject direct raw color helper imports outside low-level styling modules."""

    if file_path.as_posix().endswith("src/sqlbuild/shared/helpers/colors.py"):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == "sqlbuild.shared.helpers.colors":
            imported_names: set[str] = {alias.name for alias in node.names}
            raw_names: set[str] = imported_names - {"supports_color"}
            if raw_names:
                violations.append(
                    Violation(
                        code="SC041",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            "runtime output modules must use CliStyle instead of raw color "
                            "helpers; only supports_color may be imported from "
                            "sqlbuild.shared.helpers.colors"
                        ),
                    )
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlbuild.shared.helpers.colors":
                    violations.append(
                        Violation(
                            code="SC041",
                            path=file_path,
                            line=node.lineno,
                            message=(
                                "runtime output modules must not import "
                                "sqlbuild.shared.helpers.colors directly; use CliStyle"
                            ),
                        )
                    )
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


def check_top_level_domain_role_placement(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject direct role files or role directories under top-level runtime domains."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 4 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if relative_parts[2] == "shared":
        return []

    direct_child_name = relative_parts[3]
    if len(relative_parts) == 4 and direct_child_name in {
        "models.py",
        "types.py",
        "constants.py",
        "helpers.py",
        "classes.py",
    }:
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
        len(relative_parts) >= 5
        and direct_child_name in {"helpers", "classes"}
        and file_path.name == "__init__.py"
    ):
        return [
            Violation(
                code="SC017",
                path=file_path,
                line=None,
                message=(
                    "top-level runtime domains must not contain direct helpers/ or classes/; "
                    "move them into a subpackage or shared/"
                ),
            )
        ]

    return []


def check_top_level_domain_direct_modules(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject direct modules under top-level runtime domains except role files."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) != 4 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if file_path.name in {
        "__init__.py",
        "models.py",
        "types.py",
        "constants.py",
        "exceptions.py",
        "helpers.py",
        "providers.py",
    }:
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
    repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Keep the public sqlbuild.providers module intentionally tiny."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if relative_parts != ("src", "sqlbuild", "providers.py"):
        return []

    violations: list[Violation] = []
    public_class_names: list[str] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ClassDef):
            if node.name == "Provider":
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

    if public_class_names != ["Provider"]:
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
    repo_root: Path, file_path: Path
) -> list[Violation]:
    """Reject ad hoc direct modules in nested runtime packages outside helpers/."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 5 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if _is_orchestration_integration_public_module(relative_parts):
        return []
    if file_path.name == "main.py" and (
        relative_parts[:3]
        in {
            ("src", "sqlbuild", "adapters"),
            ("src", "sqlbuild", "integrations"),
        }
        or "shared" in relative_parts[2:-1]
    ):
        return []
    if _is_direct_child_of_main_package(relative_parts):
        return []
    if any(
        part in {"helpers", "classes", "models", "types", "constants", "exceptions"}
        for part in relative_parts[2:-1]
    ):
        return []
    if file_path.name in {
        "__init__.py",
        "models.py",
        "types.py",
        "constants.py",
        "exceptions.py",
        "helpers.py",
    }:
        return []
    if (
        len(relative_parts) >= 5
        and relative_parts[:3]
        in {
            ("src", "sqlbuild", "adapters"),
            ("src", "sqlbuild", "integrations"),
        }
        and file_path.name == "client.py"
    ):
        return []
    if (
        len(relative_parts) >= 5
        and relative_parts[:3] == ("src", "sqlbuild", "adapter")
        and file_path.name.endswith(".py")
        and file_path.name not in {"__init__.py", "main.py"}
    ):
        return []

    return [
        Violation(
            code="SC027",
            path=file_path,
            line=None,
            message=(
                "nested runtime packages must keep direct files to role-oriented modules; "
                "move additional support code under helpers/"
            ),
        )
    ]


def check_nested_runtime_package_direct_subpackages(
    repo_root: Path, file_path: Path
) -> list[Violation]:
    """Reject arbitrary direct child packages under nested runtime packages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 6 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if file_path.name != "__init__.py":
        return []

    parent_package_parts = relative_parts[:-2]
    if len(parent_package_parts) <= 3:
        return []

    parent_package_name = parent_package_parts[-1]
    direct_child_name = relative_parts[-2]
    if parent_package_name in {"helpers", "classes", "models", "types", "constants", "exceptions"}:
        return []
    if direct_child_name in {
        "helpers",
        "shared",
        "classes",
        "models",
        "types",
        "constants",
        "exceptions",
        "main",
    }:
        return []
    return [
        Violation(
            code="SC030",
            path=file_path,
            line=1,
            message=(
                "nested runtime packages must use direct subpackages only for explicit "
                "support boundaries like helpers/, shared/, classes/, or main/; move "
                "feature buckets under helpers/ or flatten them into role files"
            ),
        )
    ]


def check_main_entry_name_collisions(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject duplicate flat-module and package entry names directly under main/."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 6 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if (
        file_path.parent.name != "main"
        or file_path.suffix != ".py"
        or file_path.name == "__init__.py"
    ):
        return []
    if len(relative_parts) < 7 or relative_parts[-3] != "main":
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


def check_dev_tooling_location(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject obvious dev-tooling modules under src/sqlbuild."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 2 or relative_parts[:2] != ("src", "sqlbuild"):
        return []

    file_stem = file_path.stem
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
    """Reject helpers.py in favor of a helpers/ package."""

    if file_path.name != "helpers.py":
        return []

    return [
        Violation(
            code="SC004",
            path=file_path,
            line=None,
            message="use a helpers/ package instead of helpers.py",
        )
    ]


def check_classes_module_name(file_path: Path) -> list[Violation]:
    """Reject classes.py in favor of a classes/ package."""

    if file_path.name != "classes.py":
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
    repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Require runtime classes/ modules to define exactly one class."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 5 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if "classes" not in relative_parts[2:-1] or file_path.name == "__init__.py":
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


def check_init_module(file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate __init__.py contents."""

    if file_path.name != "__init__.py":
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


def check_types_module(file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate types.py contents."""

    if file_path.name != "types.py":
        return []

    violations: list[Violation] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.TypeAlias)):
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


def check_models_module(file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate models.py contents."""

    if file_path.name != "models.py":
        return []

    violations: list[Violation] = []
    for node in _non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ClassDef) and _is_allowed_model_class(node):
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


def check_constants_module(file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate constants.py contents."""

    if file_path.name != "constants.py":
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


def check_model_declarations_outside_models(file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject model declarations outside models.py."""

    if file_path.name == "models.py" or _is_within_role_package(file_path, "models"):
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


def check_no_raw_runtime_diagnostics(file_path: Path, module: ast.Module) -> list[Violation]:
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


def check_no_swallowed_exception_probes(file_path: Path, module: ast.Module) -> list[Violation]:
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


def check_private_definition_ordering(file_path: Path, module: ast.Module) -> list[Violation]:
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


def check_type_declarations_outside_types(file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject type-layer declarations outside types.py."""

    if file_path.name == "types.py" or _is_within_role_package(file_path, "types"):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and _is_allowed_type_class(node):
            if node.name.startswith("_") and _is_within_role_package(file_path, "helpers"):
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

        if _is_newtype_assignment(node):
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
    file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject custom exception declarations outside exceptions.py."""

    if file_path.name == "exceptions.py" or _is_within_role_package(file_path, "exceptions"):
        if _is_direct_child_of_helpers_root(file_path):
            return [
                Violation(
                    code="SC021",
                    path=file_path,
                    line=1,
                    message=(
                        "custom exceptions must not live under helpers/; "
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


def check_constants_outside_constants(file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject uppercase module-level constant assignments outside constants.py."""

    if file_path.name == "constants.py":
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


def check_helpers_package_shape(repo_root: Path, file_path: Path) -> list[Violation]:
    """Keep helpers/ shallow and free of generic entrypoints."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if "helpers" not in relative_parts[:-1]:
        return []

    helpers_index = relative_parts.index("helpers")
    if len(relative_parts) == helpers_index + 2 and file_path.name != "main.py":
        return []
    if len(relative_parts) == helpers_index + 3 and file_path.name != "main.py":
        return []

    code: str = "SC010" if len(relative_parts) == helpers_index + 2 else "SC022"
    message: str = (
        "helpers/ must not contain main.py; keep orchestration outside helper packages"
        if code == "SC010"
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


def check_shared_package_structure(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject orchestration entrypoints inside shared/ packages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if "shared" not in relative_parts[:-1]:
        return []
    shared_index = relative_parts.index("shared")
    if (
        len(relative_parts) > shared_index + 2
        and "helpers" in relative_parts[shared_index + 1 : -1]
    ):
        return []
    if file_path.name != "main.py":
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


def check_integrations_package_structure(repo_root: Path, file_path: Path) -> list[Violation]:
    """Enforce client.py instead of main.py within client-style packages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 5 or relative_parts[:3] not in {
        ("src", "sqlbuild", "adapters"),
        ("src", "sqlbuild", "integrations"),
    }:
        return []
    if file_path.name != "main.py":
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
    repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Enforce focused single-class entry modules within adapter/ subpackages."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 6 or relative_parts[:3] != ("src", "sqlbuild", "adapter"):
        return []
    if file_path.name.startswith("_") or file_path.name in {
        "main.py",
        "models.py",
        "types.py",
        "constants.py",
        "exceptions.py",
        "helpers.py",
    }:
        return []
    if any(
        part in {"helpers", "classes", "models", "types", "constants", "exceptions", "shared"}
        for part in relative_parts[3:-1]
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
    repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Enforce focused single-class client.py modules within client-style packages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if (
        file_path.name != "client.py"
        or len(relative_parts) < 5
        or relative_parts[:3]
        not in {
            ("src", "sqlbuild", "adapters"),
            ("src", "sqlbuild", "integrations"),
        }
    ):
        return []

    public_class_nodes = [
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


def check_integration_adapter_helpers_module(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject adapter-local helper modules that hide overrideable adapter behavior."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if (
        file_path.name != "helpers.py"
        or len(relative_parts) != 5
        or relative_parts[:3]
        not in {
            ("src", "sqlbuild", "adapters"),
            ("src", "sqlbuild", "integrations"),
        }
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
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
) -> list[Violation]:
    """Reject direct imports from sibling subpackages instead of parent shared/."""

    current_package_parts = _subpackage_parts(repo_root, file_path)
    if len(current_package_parts) < 3:
        return []
    if current_package_parts[-1] == "shared":
        return []

    parent_package_parts = current_package_parts[:-1]
    current_subpackage_name = current_package_parts[-1]
    violations: list[Violation] = []

    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue

        imported_parts = tuple(node.module.split("."))
        if imported_parts[: len(parent_package_parts)] != parent_package_parts:
            continue
        if len(imported_parts) <= len(parent_package_parts):
            continue

        sibling_name = imported_parts[len(parent_package_parts)]
        if sibling_name == "helpers" and current_subpackage_name in {
            "classes",
            "main",
            "models",
            "types",
            "constants",
            "exceptions",
        }:
            continue
        if sibling_name == "classes" and current_subpackage_name == "helpers":
            continue
        if sibling_name == "classes" and current_subpackage_name == "main":
            continue
        if sibling_name in {"shared", current_subpackage_name}:
            continue
        if (
            current_subpackage_name == "entry"
            and parent_package_parts[-1] == "main"
            and imported_parts[-1] == "main"
        ):
            continue
        if len(imported_parts) == len(parent_package_parts) + 1:
            continue
        if _is_allowed_sibling_public_surface(parent_package_parts, imported_parts):
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
            if _is_allowed_sibling_public_surface(parent_package_parts, imported_parts):
                continue

            sibling_name = imported_parts[len(parent_package_parts)]
            if sibling_name == "helpers" and current_subpackage_name in {
                "classes",
                "main",
                "models",
                "types",
                "constants",
                "exceptions",
            }:
                continue
            if sibling_name == "classes" and current_subpackage_name == "helpers":
                continue
            if sibling_name == "classes" and current_subpackage_name == "main":
                continue
            if sibling_name in {"shared", current_subpackage_name}:
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
    repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Reject shared/ imports that reach into sibling package internals."""

    current_package_parts = _subpackage_parts(repo_root, file_path)
    if len(current_package_parts) < 3 or current_package_parts[-1] != "shared":
        return []

    parent_package_parts = current_package_parts[:-1]
    violations: list[Violation] = []

    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_parts = tuple(node.module.split("."))
            if _is_forbidden_shared_import(parent_package_parts, imported_parts):
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
                if _is_forbidden_shared_import(parent_package_parts, imported_parts):
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
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
) -> list[Violation]:
    """Block imports that reach into another domain package's internal structure."""

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 4 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    top_level_domain: str = relative_parts[2]
    if top_level_domain in {"spec", "adapter"}:
        return []

    current_domain_parts: tuple[str, ...] = relative_parts[2:]
    current_domain: str = current_domain_parts[0]
    current_subdomain: str | None = (
        current_domain_parts[1] if len(current_domain_parts) > 2 else None
    )

    violations: list[Violation] = []
    _DEEP_INTERNAL_SEGMENTS: frozenset[str] = frozenset({"shared", "helpers", "classes"})
    _PUBLIC_MODULES: frozenset[str] = frozenset(
        {"models", "types", "constants", "exceptions", "__init__", "main"}
    )

    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        imported_parts: tuple[str, ...] = tuple(node.module.split("."))
        if len(imported_parts) < 3 or imported_parts[0] != "sqlbuild":
            continue

        imported_domain: str = imported_parts[1]
        if imported_domain == current_domain:
            if len(imported_parts) < 4:
                continue
            imported_subdomain: str = imported_parts[2]
            if current_subdomain is not None and imported_subdomain == current_subdomain:
                continue
            if imported_subdomain == "shared":
                continue
            if len(imported_parts) >= 4 and imported_parts[3] in _PUBLIC_MODULES:
                continue
            if len(imported_parts) == 3:
                continue
            if _has_deep_internal_segment(imported_parts[3:], _DEEP_INTERNAL_SEGMENTS):
                violations.append(
                    Violation(
                        code="SC033",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            f"cross-package import reaches into internal structure of "
                            f"'{'.'.join(imported_parts[:3])}'; import from its public "
                            f"surface (models, types, constants, exceptions, or a thin "
                            f"main/ entry module). If the code is helper logic rather than "
                            f"an entrypoint, move it to helpers/ or, if broadly reused "
                            f"across domains, shared/"
                        ),
                    )
                )
            continue

        if imported_domain in {"spec", "adapter", "shared"}:
            continue

        if len(imported_parts) >= 4:
            target_module: str = imported_parts[2]
            if target_module in _PUBLIC_MODULES:
                continue
            if _has_deep_internal_segment(imported_parts[2:], _DEEP_INTERNAL_SEGMENTS):
                violations.append(
                    Violation(
                        code="SC033",
                        path=file_path,
                        line=node.lineno,
                        message=(
                            f"cross-package import reaches into internal structure of "
                            f"'{'.'.join(imported_parts[:2])}'; import from its public "
                            f"surface (models, types, constants, exceptions, or a thin "
                            f"main/ entry module). If the code is helper logic rather than "
                            f"an entrypoint, move it to helpers/ or, if broadly reused "
                            f"across domains, shared/"
                        ),
                    )
                )

    return violations


def _has_deep_internal_segment(parts: tuple[str, ...], internal_segments: frozenset[str]) -> bool:
    """Check whether any segment in the import path is a deep internal boundary."""

    return any(seg in internal_segments for seg in parts)


def _adapter_contract_class_names(
    *, repo_root: Path, file_path: Path, module: ast.Module
) -> frozenset[str]:
    indexed_names: frozenset[str] = _builtin_adapter_contract_class_names_by_path(
        repo_root=repo_root
    ).get(file_path.resolve(), frozenset())
    if indexed_names:
        return indexed_names

    relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    if relative_parts[:3] not in {
        ("src", "sqlbuild", "adapters"),
        ("src", "sqlbuild", "integrations"),
    }:
        return frozenset()
    if file_path.name != "client.py" and relative_parts[-3:] != (
        "shared",
        "classes",
        "duckdb.py",
    ):
        return frozenset()
    return frozenset(
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Adapter")
    )


def _builtin_adapter_contract_class_names_by_path(*, repo_root: Path) -> dict[Path, frozenset[str]]:
    try:
        from sqlbuild.adapter.base.base_adapter import BaseAdapter
        from sqlbuild.adapter.shared.helpers.builtins import builtin_adapter_classes
    except Exception:
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
        from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
    except Exception:
        return frozenset()

    return frozenset(getattr(StrictAdapter, "__abstractmethods__", frozenset()))


def _is_base_adapter_method_alias(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return isinstance(node.value, ast.Attribute) and _is_name(node.value.value, "BaseAdapter")
    if isinstance(node, ast.AnnAssign):
        return (
            node.value is not None
            and isinstance(node.value, ast.Attribute)
            and _is_name(node.value.value, "BaseAdapter")
        )
    return False


def _is_super_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _is_name(node.func, "super")


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def check_entry_module_shape(file_path: Path, module: ast.Module) -> list[Violation]:
    """Enforce entry modules as focused single-entry surfaces."""

    if not _is_entry_module(file_path):
        return []
    if _is_orchestration_integration_public_entry(file_path):
        return []

    public_function_nodes = [
        node
        for node in _non_docstring_body(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    private_function_nodes = [
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

    if len(private_function_nodes) > 2:
        violations.append(
            Violation(
                code="SC026",
                path=file_path,
                line=private_function_nodes[2].lineno,
                message=(
                    "entry modules must define at most two private top-level functions; "
                    "extract additional behavior to sibling modules under main/ or helpers/ "
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


def is_docstring_only_module(module: ast.Module) -> bool:
    """Return whether the module body is empty or docstring-only."""

    body = module.body
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
        file_path.suffix == ".py"
        and file_path.name not in {"__init__.py", "main.py"}
        and file_path.parent.name == "main"
    )


def _is_direct_child_of_helpers_root(file_path: Path) -> bool:
    parts = file_path.parts
    if "helpers" not in parts[:-1]:
        return False
    helpers_index = parts.index("helpers")
    return len(parts) == helpers_index + 2


def _is_string_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_allowed_type_class(node: ast.ClassDef) -> bool:
    if _is_dataclass_class(node) or _inherits_from_base_names(node, MODEL_CLASS_BASE_NAMES):
        return False
    return _inherits_from_base_names(node, TYPE_CLASS_BASE_NAMES)


def _is_allowed_model_class(node: ast.ClassDef) -> bool:
    if node.name.startswith("_"):
        return False
    return _is_dataclass_class(node) or _inherits_from_base_names(node, MODEL_CLASS_BASE_NAMES)


def _is_exception_class(node: ast.ClassDef) -> bool:
    """Return whether a class definition looks like a custom exception."""

    if node.name.endswith(("Error", "Exception")):
        return True

    return any(
        (base_name or "").endswith(("Error", "Exception"))
        for base_name in (_base_name(base) for base in node.bases)
    )


def _is_dataclass_class(node: ast.ClassDef) -> bool:
    return any(
        _decorator_name(decorator).endswith("dataclass") for decorator in node.decorator_list
    )


def _inherits_from_base_names(node: ast.ClassDef, base_names: frozenset[str]) -> bool:
    return any(_base_name(base) in base_names for base in node.bases)


def _is_local_model_union_alias(
    *, file_path: Path, module: ast.Module, node: ast.TypeAlias
) -> bool:
    if not _is_within_role_package(file_path, "models"):
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
    if len(union_member_names) < 2:
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
    return "src" in parts and "sqlbuild" in parts and file_path.suffix == ".py"


def _raise_uses_raw_builtin(node: ast.Raise) -> bool:
    if node.exc is None:
        return False
    raised_name: str | None = (
        _base_name(node.exc.func) if isinstance(node.exc, ast.Call) else _base_name(node.exc)
    )
    return raised_name in RAW_BUILTIN_RAISE_NAMES


def _is_bare_exception_handler(node: ast.ExceptHandler) -> bool:
    return node.name is None and isinstance(node.type, ast.Name) and node.type.id == "Exception"


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
        parent = _decorator_name(node.value)
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

    return _base_name(value.func) == "NewType"


def _is_within_role_package(file_path: Path, role_directory_name: str) -> bool:
    return role_directory_name in file_path.parts[:-1]


def _is_direct_child_of_main_package(relative_parts: tuple[str, ...]) -> bool:
    return (
        len(relative_parts) >= 2
        and relative_parts[-2] == "main"
        and relative_parts[-1] != "main.py"
    )


def _is_orchestration_integration_public_module(relative_parts: tuple[str, ...]) -> bool:
    return (
        len(relative_parts) == 5
        and relative_parts[:3] == ("src", "sqlbuild", "integrations")
        and relative_parts[3] in {"dagster", "rivers"}
        and relative_parts[-1] in {"assets.py", "translator.py", "project.py", "resource.py"}
    )


def _is_orchestration_integration_public_init(file_path: Path) -> bool:
    parts: tuple[str, ...] = file_path.parts
    return (
        len(parts) >= 5
        and parts[-5:-2] == ("src", "sqlbuild", "integrations")
        and parts[-2] in {"dagster", "rivers"}
        and parts[-1] == "__init__.py"
    )


def _is_orchestration_integration_public_entry(file_path: Path) -> bool:
    parts: tuple[str, ...] = file_path.parts
    return (
        len(parts) >= 5
        and parts[-5:-2] == ("src", "sqlbuild", "integrations")
        and parts[-2] in {"dagster", "rivers"}
    )


def _subpackage_parts(repo_root: Path, file_path: Path) -> tuple[str, ...]:
    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).with_suffix("").parts

    if len(relative_parts) >= 4 and relative_parts[:2] == ("src", "sqlbuild"):
        package_parts = relative_parts[1:-1]
    elif len(relative_parts) >= 3 and relative_parts[0] == "scripts":
        package_parts = relative_parts[:-1]
    else:
        return ()

    return tuple(package_parts)


def _is_forbidden_shared_import(
    parent_package_parts: tuple[str, ...],
    imported_parts: tuple[str, ...],
) -> bool:
    if imported_parts[: len(parent_package_parts)] != parent_package_parts:
        return False
    if len(imported_parts) <= len(parent_package_parts):
        return False

    next_segment = imported_parts[len(parent_package_parts)]
    if next_segment == "shared":
        return False

    return len(imported_parts) > len(parent_package_parts) + 1


def _is_allowed_sibling_public_surface(
    parent_package_parts: tuple[str, ...],
    imported_parts: tuple[str, ...],
) -> bool:
    public_surface_names: frozenset[str] = frozenset({"models", "types", "constants", "exceptions"})
    if (
        len(imported_parts) == len(parent_package_parts) + 2
        and imported_parts[len(parent_package_parts)] == "main"
        and imported_parts[-1] != "main"
    ):
        return True
    if (
        len(imported_parts) == len(parent_package_parts) + 2
        and imported_parts[len(parent_package_parts)] in public_surface_names
    ):
        return True
    if (
        len(imported_parts) == len(parent_package_parts) + 3
        and imported_parts[len(parent_package_parts) + 1] in public_surface_names
    ):
        return True
    if len(imported_parts) != len(parent_package_parts) + 2:
        return False

    public_module_name: str = imported_parts[-1]
    if public_module_name in public_surface_names:
        return True
    if "adapter" in parent_package_parts:
        return True
    return False
