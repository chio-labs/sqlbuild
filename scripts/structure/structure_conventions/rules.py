"""Rule implementations for structure convention checks."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.structure.structure_conventions.constants import (
    BANNED_GENERIC_FILENAMES,
    DEV_TOOLING_FILE_PREFIXES,
    DEV_TOOLING_SEGMENTS,
    MODEL_CLASS_BASE_NAMES,
    TYPE_CLASS_BASE_NAMES,
)
from scripts.structure.structure_conventions.models import Violation


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
    """Reject direct modules under top-level runtime domains except __init__.py and main.py."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) != 4 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if file_path.name in {
        "__init__.py",
        "main.py",
        "models.py",
        "types.py",
        "constants.py",
        "helpers.py",
    }:
        return []

    return [
        Violation(
            code="SC018",
            path=file_path,
            line=None,
            message=(
                "top-level runtime domains must contain subpackages, not direct modules; "
                "keep direct files limited to __init__.py or main.py"
            ),
        )
    ]


def check_nested_runtime_package_direct_modules(
    repo_root: Path, file_path: Path
) -> list[Violation]:
    """Reject ad hoc direct modules in nested runtime packages outside helpers/."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 5 or relative_parts[:2] != ("src", "sqlbuild"):
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
        "main.py",
        "models.py",
        "types.py",
        "constants.py",
        "exceptions.py",
        "helpers.py",
    }:
        return []
    if (
        len(relative_parts) >= 5
        and relative_parts[:3] == ("src", "sqlbuild", "integrations")
        and file_path.name == "client.py"
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
    if parent_package_name == "main":
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


def check_main_command_package_entry_surface(repo_root: Path, file_path: Path) -> list[Violation]:
    """Require packages directly under main/ to expose their entry via main.py."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 7 or relative_parts[:2] != ("src", "sqlbuild"):
        return []
    if file_path.name != "__init__.py":
        return []
    if file_path.parent.parent.name != "main":
        return []
    if file_path.parent.name == "shared":
        return []
    if (file_path.parent / "main.py").exists():
        return []

    return [
        Violation(
            code="SC028",
            path=file_path,
            line=1,
            message=("packages directly under main/ must expose their public entry from main.py"),
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


def check_init_module(file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate __init__.py contents."""

    if file_path.name != "__init__.py":
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


def check_type_declarations_outside_types(file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject type-layer declarations outside types.py."""

    if file_path.name == "types.py" or _is_within_role_package(file_path, "types"):
        return []

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and _is_allowed_type_class(node):
            violations.append(
                Violation(
                    code="SC015",
                    path=file_path,
                    line=node.lineno,
                    message="type-layer declarations must be defined in types.py",
                )
            )
            continue

        if isinstance(node, ast.TypeAlias):
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


def check_helpers_package_structure(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject orchestration entrypoints inside helpers/ packages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if "helpers" not in relative_parts[:-1]:
        return []
    if file_path.name != "main.py":
        return []
    if not _is_direct_child_of_helpers_root(file_path):
        return []

    return [
        Violation(
            code="SC010",
            path=file_path,
            line=None,
            message="helpers/ must not contain main.py; keep orchestration outside helper packages",
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
    """Enforce client.py instead of main.py within integrations/ packages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 5 or relative_parts[:3] != ("src", "sqlbuild", "integrations"):
        return []
    if file_path.name != "main.py":
        return []

    return [
        Violation(
            code="SC023",
            path=file_path,
            line=None,
            message=(
                "integrations/ packages must use client.py instead of main.py for primary client "
                "entrypoints"
            ),
        )
    ]


def check_helpers_subpackage_shape(repo_root: Path, file_path: Path) -> list[Violation]:
    """Reject ad hoc direct modules inside helper subpackages."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if "helpers" not in relative_parts[:-1]:
        return []

    helpers_index = relative_parts.index("helpers")
    if "helpers" in relative_parts[helpers_index + 1 : -1]:
        return []
    if len(relative_parts) <= helpers_index + 2:
        return []

    if file_path.name in {
        "__init__.py",
        "main.py",
        "models.py",
        "types.py",
        "constants.py",
        "exceptions.py",
        "helpers.py",
    }:
        return []

    return [
        Violation(
            code="SC022",
            path=file_path,
            line=None,
            message=(
                "helper subpackages must use role-oriented files like models.py, "
                "types.py, constants.py, exceptions.py, or nested helpers/ packages "
                "instead of ad hoc modules"
            ),
        )
    ]


def check_client_module_shape(
    repo_root: Path, file_path: Path, module: ast.Module
) -> list[Violation]:
    """Enforce focused single-class client.py modules within integrations/."""

    relative_parts = file_path.resolve().relative_to(repo_root.resolve()).parts
    if (
        file_path.name != "client.py"
        or len(relative_parts) < 5
        or relative_parts[:3] != ("src", "sqlbuild", "integrations")
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
                message="integrations client.py must define exactly one public top-level class",
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
                message="integrations client.py must contain only imports and top-level classes",
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


def check_main_module_shape(file_path: Path, module: ast.Module) -> list[Violation]:
    """Enforce main entry modules as focused single-entry surfaces."""

    if not _is_main_entry_module(file_path):
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
                message=("main entry modules must define exactly one public top-level function"),
            )
        )

    if len(private_function_nodes) > 4:
        violations.append(
            Violation(
                code="SC026",
                path=file_path,
                line=private_function_nodes[4].lineno,
                message=(
                    "main entry modules must define at most four private top-level functions; "
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
                message="main entry modules must contain only imports and top-level functions",
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


def _is_main_entry_module(file_path: Path) -> bool:
    if file_path.name == "main.py":
        return True
    return (
        file_path.suffix == ".py"
        and file_path.name != "__init__.py"
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


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


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
    return len(relative_parts) >= 2 and relative_parts[-2] == "main"


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
    if (
        parent_package_parts[-2:] == ("main", "entry")
        and len(imported_parts) == len(parent_package_parts) + 1
        and imported_parts[-1] == "main"
    ):
        return True
    if len(imported_parts) != len(parent_package_parts) + 2:
        return False

    public_module_name = imported_parts[-1]
    return public_module_name in {"models", "types"}
