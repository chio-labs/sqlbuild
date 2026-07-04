"""Rule implementations for test convention checks."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.testing.test_conventions.ast_utils import (
    attribute_chain,
    extract_name_constant,
    is_dataclass_decorator,
    is_docstring_only_module,
    is_parametrize_decorator,
)
from scripts.testing.test_conventions.constants import TEST_NAME_PATTERN, VALID_TEST_SCOPES
from scripts.testing.test_conventions.filesystem import module_name_for_file
from scripts.testing.test_conventions.models import LocalTestTypesInfo, ModuleContext, Violation


def parse_python_module(file_path: Path) -> ast.Module:
    """Parse a Python file into an AST module."""

    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def check_test_directory_path(repo_root: Path, test_directory: Path) -> list[Violation]:
    """Validate scope and mirrored layout for test directories."""

    relative_parts = test_directory.resolve().relative_to(repo_root.resolve()).parts
    if len(relative_parts) < 3 or relative_parts[0] != "tests":
        return [
            Violation(
                code="TC028",
                path=test_directory,
                line=None,
                message="test directories must live under tests/<scope>/...",
            )
        ]

    scope = relative_parts[1]
    if scope not in VALID_TEST_SCOPES:
        valid_scopes = ", ".join(sorted(VALID_TEST_SCOPES))
        return [
            Violation(
                code="TC029",
                path=test_directory,
                line=None,
                message=f"test scope must be one of: {valid_scopes}",
            )
        ]

    mirrored_root = relative_parts[2]
    if mirrored_root == "src":
        return _check_src_mirroring(repo_root, test_directory, relative_parts)

    if mirrored_root == "scripts":
        return _check_scripts_mirroring(repo_root, test_directory, relative_parts)

    return [
        Violation(
            code="TC030",
            path=test_directory,
            line=None,
            message="test directories must mirror either src/... or scripts/... within each scope",
        )
    ]


def _check_src_mirroring(
    repo_root: Path,
    test_directory: Path,
    relative_parts: tuple[str, ...],
) -> list[Violation]:
    if len(relative_parts) < 5:
        return [
            Violation(
                code="TC031",
                path=test_directory,
                line=None,
                message=("src-backed tests must live under tests/<scope>/src/<package>/<area>/..."),
            )
        ]

    package_path = repo_root / "src" / relative_parts[3]
    if not package_path.is_dir():
        return [
            Violation(
                code="TC032",
                path=test_directory,
                line=None,
                message=(
                    "tests under tests/<scope>/src must mirror a real package directory under src/"
                ),
            )
        ]

    area_path = package_path / relative_parts[4]
    if not area_path.exists():
        if (
            relative_parts[3] == "sqlbuild"
            and relative_parts[4] == "providers"
            and (package_path / "providers.py").is_file()
        ):
            return []
        return [
            Violation(
                code="TC033",
                path=test_directory,
                line=None,
                message=(
                    "tests under tests/<scope>/src must mirror a real src/<package>/<area> path"
                ),
            )
        ]

    return []


def _check_scripts_mirroring(
    repo_root: Path,
    test_directory: Path,
    relative_parts: tuple[str, ...],
) -> list[Violation]:
    if len(relative_parts) < 4:
        return [
            Violation(
                code="TC034",
                path=test_directory,
                line=None,
                message="script-backed tests must live under tests/<scope>/scripts/<area>/...",
            )
        ]

    area_path = repo_root / "scripts" / relative_parts[3]
    if not area_path.exists():
        return [
            Violation(
                code="TC035",
                path=test_directory,
                line=None,
                message=(
                    "tests under tests/<scope>/scripts must mirror a real scripts/<area> path"
                ),
            )
        ]

    return []


def check_init_module(repo_root: Path, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate __init__.py contents."""

    if is_docstring_only_module(module):
        return []
    return [
        Violation(
            code="TC001",
            path=file_path,
            line=1,
            message="__init__.py must be empty or docstring-only",
        )
    ]


def check_no_relative_imports(file_path: Path, module: ast.Module) -> list[Violation]:
    """Reject relative imports in test directories."""

    violations: list[Violation] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            violations.append(
                Violation(
                    code="TC002",
                    path=file_path,
                    line=node.lineno,
                    message="test modules must use absolute imports, not relative imports",
                )
            )
    return violations


def check_test_types_file(
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
) -> tuple[LocalTestTypesInfo, list[Violation]]:
    """Validate local _test_types.py declarations."""

    dataclass_names: set[str] = set()
    violations: list[Violation] = []

    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(is_dataclass_decorator(decorator) for decorator in node.decorator_list):
            continue

        dataclass_names.add(node.name)
        field_names = {
            statement.target.id
            for statement in node.body
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
        }

        if "description" not in field_names:
            violations.append(
                Violation(
                    code="TC003",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        f"dataclass '{node.name}' in _test_types.py must define "
                        "a 'description' field"
                    ),
                )
            )

        if not any(field_name.startswith("expected_") for field_name in field_names):
            violations.append(
                Violation(
                    code="TC004",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        f"dataclass '{node.name}' in _test_types.py must define at least one "
                        "'expected_' field"
                    ),
                )
            )

    return (
        LocalTestTypesInfo(
            module_name=module_name_for_file(repo_root, file_path),
            dataclass_names=frozenset(dataclass_names),
        ),
        violations,
    )


def check_scenario_models_file(file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate local scenario_models.py declarations."""

    violations: list[Violation] = []

    for node in module.body:
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            if isinstance(node.value.value, str):
                continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ClassDef):
            if any(is_dataclass_decorator(decorator) for decorator in node.decorator_list):
                continue
            violations.append(
                Violation(
                    code="TC028",
                    path=file_path,
                    line=node.lineno,
                    message=("scenario_models.py must contain only dataclass model declarations"),
                )
            )
            continue
        violations.append(
            Violation(
                code="TC028",
                path=file_path,
                line=getattr(node, "lineno", 1),
                message="scenario_models.py must contain only dataclass model declarations",
            )
        )

    return violations


def build_module_context(
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
    local_test_types: LocalTestTypesInfo,
) -> tuple[ModuleContext, list[Violation]]:
    """Build reusable module metadata for test checks."""

    expected_test_types_module = module_name_for_file(
        repo_root, file_path.parent / "_test_types.py"
    )
    imported_local_test_case_types: set[str] = set()
    violations: list[Violation] = []

    for node in module.body:
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.module == expected_test_types_module:
            for imported_name in node.names:
                if imported_name.name in local_test_types.dataclass_names:
                    imported_local_test_case_types.add(imported_name.asname or imported_name.name)

        elif node.module and node.module.endswith("._test_types"):
            violations.append(
                Violation(
                    code="TC005",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "test files must import test case dataclasses "
                        "from their local _test_types.py"
                    ),
                )
            )

    test_case_annotation_names: set[str] = set(imported_local_test_case_types)
    module_level_case_lists: dict[str, ast.expr] = {}
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_level_case_lists[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                module_level_case_lists[node.target.id] = node.value

    return (
        ModuleContext(
            imported_local_test_case_types=frozenset(imported_local_test_case_types),
            test_case_annotation_names=frozenset(test_case_annotation_names),
            module_level_case_lists=module_level_case_lists,
        ),
        violations,
    )


def check_test_file(
    file_path: Path,
    module: ast.Module,
    local_test_types: LocalTestTypesInfo,
    context: ModuleContext,
) -> list[Violation]:
    """Validate test module structure and test functions."""

    violations: list[Violation] = []

    if not file_path.name.startswith("test_"):
        violations.append(
            Violation(
                code="TC006",
                path=file_path,
                line=1,
                message="test file names must start with 'test_'",
            )
        )

    violations.extend(_check_top_level_test_module_shape(file_path, module))

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            violations.extend(_check_test_function(file_path, node, local_test_types, context))

    return violations


def _check_top_level_test_module_shape(file_path: Path, module: ast.Module) -> list[Violation]:
    if file_path.name == "_test_helpers.py":
        return []

    violations: list[Violation] = []
    first_test_function_line: int | None = None

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "test_"
        ):
            violations.append(
                Violation(
                    code="TC027",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "top-level helper functions are not allowed in test modules; "
                        "move shared helpers to local helpers.py or _test_helpers.py, "
                        "or fixtures to conftest.py"
                    ),
                )
            )
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            and first_test_function_line is None
        ):
            first_test_function_line = node.lineno
        if _is_test_case_list_assignment(node):
            violations.append(
                Violation(
                    code="TC015",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "module-level TEST_CASES and *_TEST_CASES lists are not allowed; "
                        "inline dataclass cases in @pytest.mark.parametrize"
                    ),
                )
            )
        if first_test_function_line is not None and _is_private_assignment(node):
            violations.append(
                Violation(
                    code="TC037",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "private constant definitions must appear before "
                        "test function definitions at module level"
                    ),
                )
            )

    return violations


def _is_private_assignment(node: ast.stmt) -> bool:
    """Return whether a node is a private module-level assignment."""

    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id.startswith("_")
    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name) and target.id.startswith("_") for target in node.targets
        )
    return False


def _is_test_case_list_assignment(node: ast.stmt) -> bool:
    """Return whether a node assigns a module-level test case list."""

    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return _is_multi_case_list_name(node.target.id)
    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name) and _is_multi_case_list_name(target.id)
            for target in node.targets
        )
    return False


def _check_test_function(
    file_path: Path,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    local_test_types: LocalTestTypesInfo,
    context: ModuleContext,
) -> list[Violation]:
    violations: list[Violation] = []

    if not TEST_NAME_PATTERN.match(function_node.name):
        violations.append(
            Violation(
                code="TC007",
                path=file_path,
                line=function_node.lineno,
                message="test name must follow test_given_<state>_when_<action>_then_<expectation>",
            )
        )

    parametrize = next(
        (
            decorator
            for decorator in function_node.decorator_list
            if is_parametrize_decorator(decorator)
        ),
        None,
    )
    if not isinstance(parametrize, ast.Call):
        violations.append(
            Violation(
                code="TC008",
                path=file_path,
                line=function_node.lineno,
                message="tests must use @pytest.mark.parametrize with a dataclass-backed test_case",
            )
        )
        return violations

    test_case_arg = next(
        (argument for argument in function_node.args.args if argument.arg == "test_case"),
        None,
    )
    if test_case_arg is None:
        violations.append(
            Violation(
                code="TC009",
                path=file_path,
                line=function_node.lineno,
                message="tests must accept a 'test_case' parameter",
            )
        )
    elif not isinstance(test_case_arg.annotation, ast.Name) or (
        test_case_arg.annotation.id not in context.test_case_annotation_names
    ):
        violations.append(
            Violation(
                code="TC010",
                path=file_path,
                line=function_node.lineno,
                message=(
                    "'test_case' must be annotated with a dataclass "
                    "imported from the local _test_types.py"
                ),
            )
        )

    violations.extend(_check_parametrize_shape(file_path, function_node, parametrize, context))
    violations.extend(_check_no_if_statements(file_path, function_node))

    if not _references_expected_field(function_node):
        violations.append(
            Violation(
                code="TC011",
                path=file_path,
                line=function_node.lineno,
                message="tests must assert against at least one 'test_case.expected_' field",
            )
        )

    return violations


def _check_no_if_statements(
    file_path: Path,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[Violation]:
    violations: list[Violation] = []

    node: ast.AST
    for node in ast.walk(function_node):
        if isinstance(node, ast.If):
            violations.append(
                Violation(
                    code="TC036",
                    path=file_path,
                    line=node.lineno,
                    message=(
                        "test functions must not contain if statements; split distinct setup "
                        "or assertion paths into separate test functions instead of hiding "
                        "branches in helpers"
                    ),
                )
            )

    return violations


def _check_parametrize_shape(
    file_path: Path,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.Call,
    context: ModuleContext,
) -> list[Violation]:
    violations: list[Violation] = []

    if len(decorator.args) < 2:
        return [
            Violation(
                code="TC012",
                path=file_path,
                line=function_node.lineno,
                message="@pytest.mark.parametrize must declare the parameter name and case values",
            )
        ]

    parameter_name = extract_name_constant(decorator.args[0])
    if parameter_name != "test_case":
        violations.append(
            Violation(
                code="TC013",
                path=file_path,
                line=function_node.lineno,
                message="@pytest.mark.parametrize must parameterize the 'test_case' argument",
            )
        )

    ids_expression = next(
        (keyword.value for keyword in decorator.keywords if keyword.arg == "ids"), None
    )
    if ids_expression is None:
        violations.append(
            Violation(
                code="TC014",
                path=file_path,
                line=function_node.lineno,
                message="@pytest.mark.parametrize must define explicit ids",
            )
        )

    values_expression = decorator.args[1]
    if isinstance(values_expression, ast.Name):
        violations.append(
            Violation(
                code="TC016",
                path=file_path,
                line=function_node.lineno,
                message=(
                    "@pytest.mark.parametrize values must be inline local test case "
                    "dataclass instances"
                ),
            )
        )
        return violations

    if isinstance(values_expression, ast.ListComp):
        if not _is_local_test_case_constructor(values_expression.elt, context):
            violations.append(
                Violation(
                    code="TC024",
                    path=file_path,
                    line=getattr(values_expression.elt, "lineno", function_node.lineno),
                    message=(
                        "inline generated test cases must construct dataclasses imported "
                        "from the local _test_types.py"
                    ),
                )
            )
        if not _is_description_lambda_ids(ids_expression):
            violations.append(
                Violation(
                    code="TC025",
                    path=file_path,
                    line=function_node.lineno,
                    message=(
                        "@pytest.mark.parametrize ids must be ids=lambda case: case.description"
                    ),
                )
            )
        return violations

    if not isinstance(values_expression, (ast.List, ast.Tuple)):
        violations.append(
            Violation(
                code="TC021",
                path=file_path,
                line=function_node.lineno,
                message=(
                    "@pytest.mark.parametrize values must be inline local test case "
                    "dataclass instances"
                ),
            )
        )
        return violations

    if not values_expression.elts:
        violations.append(
            Violation(
                code="TC022",
                path=file_path,
                line=function_node.lineno,
                message="inline parametrization must include at least one test case",
            )
        )
    for element in values_expression.elts:
        if isinstance(element, ast.Dict):
            violations.append(
                Violation(
                    code="TC023",
                    path=file_path,
                    line=element.lineno,
                    message="test cases must use local dataclass instances, not dict literals",
                )
            )
        elif not _is_local_test_case_constructor(element, context):
            violations.append(
                Violation(
                    code="TC024",
                    path=file_path,
                    line=getattr(element, "lineno", function_node.lineno),
                    message=(
                        "inline test cases must be constructor calls to dataclasses "
                        "imported from the local _test_types.py"
                    ),
                )
            )

    if not _is_description_lambda_ids(ids_expression):
        violations.append(
            Violation(
                code="TC025",
                path=file_path,
                line=function_node.lineno,
                message=("@pytest.mark.parametrize ids must be ids=lambda case: case.description"),
            )
        )

    return violations


def _references_expected_field(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(function_node):
        if isinstance(node, ast.Attribute):
            chain = attribute_chain(node)
            if (
                chain
                and len(chain) >= 2
                and chain[0] == "test_case"
                and chain[-1].startswith("expected_")
            ):
                return True
    return False


def _is_local_test_case_constructor(expression: ast.expr, context: ModuleContext) -> bool:
    if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name):
        return expression.func.id in context.imported_local_test_case_types
    return False


def _is_multi_case_list_name(name: str) -> bool:
    return name == "TEST_CASES" or name.endswith("_TEST_CASES")


def _is_description_lambda_ids(expression: ast.expr | None) -> bool:
    if not isinstance(expression, ast.Lambda):
        return False
    if len(expression.args.args) != 1:
        return False
    if expression.args.args[0].arg != "case":
        return False
    return attribute_chain(expression.body) == ("case", "description")
