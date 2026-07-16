"""Rule implementations for test convention checks."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.testing._helpers.ast_utils import (
    attribute_chain,
    extract_name_constant,
    is_dataclass_decorator,
    is_docstring_only_module,
    is_parametrize_decorator,
)
from scripts.testing._helpers.filesystem import module_name_for_file
from scripts.testing.constants import (
    DESCRIPTION_FIELD_NAME,
    DESCRIPTION_IDS_PARAMETER_NAME,
    EXPECTED_FIELD_PREFIX,
    FILE_BACKED_TEST_AREAS,
    PARAMETRIZE_IDS_KEYWORD,
    PYTHON_FILE_SUFFIX,
    SOURCE_ROOT_DIRECTORY_NAME,
    TEST_CASE_COLLECTION_NAME,
    TEST_CASE_COLLECTION_SUFFIX,
    TEST_CASE_PARAMETER_NAME,
    TEST_FUNCTION_PREFIX,
    TEST_HELPERS_FILENAME,
    TEST_NAME_PATTERN,
    TEST_ROOT_DIRECTORY_NAME,
    TEST_TYPES_FILENAME,
    TOOLING_ROOT_DIRECTORY_NAME,
    VALID_TEST_SCOPES,
)
from scripts.testing.models import LocalTestTypesInfo, ModuleContext, Violation


def parse_python_module(file_path: Path) -> ast.Module:
    """Parse a Python file into an AST module."""

    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def check_test_directory_path(*, repo_root: Path, test_directory: Path) -> list[Violation]:
    """Validate scope and mirrored layout for test directories."""

    relative_parts: tuple[str, ...] = (
        test_directory.resolve().relative_to(repo_root.resolve()).parts
    )
    scoped_test_path_part_count: int = 3
    if (
        len(relative_parts) < scoped_test_path_part_count
        or relative_parts[0] != TEST_ROOT_DIRECTORY_NAME
    ):
        return [
            Violation(
                code="TC028",
                path=test_directory,
                line=None,
                message="test directories must live under tests/<scope>/...",
            )
        ]

    scope: str = relative_parts[1]
    if scope not in VALID_TEST_SCOPES:
        valid_scopes: str = ", ".join(sorted(VALID_TEST_SCOPES))
        return [
            Violation(
                code="TC029",
                path=test_directory,
                line=None,
                message=f"test scope must be one of: {valid_scopes}",
            )
        ]

    mirrored_root: str = relative_parts[2]
    if mirrored_root == SOURCE_ROOT_DIRECTORY_NAME:
        return _check_src_mirroring(
            repo_root=repo_root, test_directory=test_directory, relative_parts=relative_parts
        )

    if mirrored_root == TOOLING_ROOT_DIRECTORY_NAME:
        return _check_scripts_mirroring(
            repo_root=repo_root, test_directory=test_directory, relative_parts=relative_parts
        )

    return [
        Violation(
            code="TC030",
            path=test_directory,
            line=None,
            message="test directories must mirror either src/... or scripts/... within each scope",
        )
    ]


def _check_src_mirroring(
    *,
    repo_root: Path,
    test_directory: Path,
    relative_parts: tuple[str, ...],
) -> list[Violation]:
    mirrored_src_area_part_count: int = 5
    if len(relative_parts) < mirrored_src_area_part_count:
        return [
            Violation(
                code="TC031",
                path=test_directory,
                line=None,
                message=("src-backed tests must live under tests/<scope>/src/<package>/<area>/..."),
            )
        ]

    package_path: Path = repo_root / SOURCE_ROOT_DIRECTORY_NAME / relative_parts[3]
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

    area_path: Path = package_path / relative_parts[4]
    if not area_path.exists():
        if (relative_parts[3], relative_parts[4]) in FILE_BACKED_TEST_AREAS and (
            package_path / f"{relative_parts[4]}{PYTHON_FILE_SUFFIX}"
        ).is_file():
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
    *,
    repo_root: Path,
    test_directory: Path,
    relative_parts: tuple[str, ...],
) -> list[Violation]:
    mirrored_script_area_part_count: int = 4
    if len(relative_parts) < mirrored_script_area_part_count:
        return [
            Violation(
                code="TC034",
                path=test_directory,
                line=None,
                message="script-backed tests must live under tests/<scope>/scripts/<area>/...",
            )
        ]

    area_path: Path = repo_root / TOOLING_ROOT_DIRECTORY_NAME / relative_parts[3]
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


def check_init_module(*, repo_root: Path, file_path: Path, module: ast.Module) -> list[Violation]:
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


def check_no_relative_imports(*, file_path: Path, module: ast.Module) -> list[Violation]:
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
    *,
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
        field_names: set[str] = {
            statement.target.id
            for statement in node.body
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
        }

        if DESCRIPTION_FIELD_NAME not in field_names:
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

        if not any(field_name.startswith(EXPECTED_FIELD_PREFIX) for field_name in field_names):
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
            module_name=module_name_for_file(repo_root=repo_root, file_path=file_path),
            dataclass_names=frozenset(dataclass_names),
        ),
        violations,
    )


def check_scenario_models_file(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate local scenario_models.py declarations."""

    violations: list[Violation] = []

    for node in module.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
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
    *,
    repo_root: Path,
    file_path: Path,
    module: ast.Module,
    local_test_types: LocalTestTypesInfo,
) -> tuple[ModuleContext, list[Violation]]:
    """Build reusable module metadata for test checks."""

    expected_test_types_module: str = module_name_for_file(
        repo_root=repo_root, file_path=file_path.parent / TEST_TYPES_FILENAME
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

        elif node.module and node.module.endswith(
            f".{TEST_TYPES_FILENAME.removesuffix(PYTHON_FILE_SUFFIX)}"
        ):
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
    *,
    file_path: Path,
    module: ast.Module,
    local_test_types: LocalTestTypesInfo,
    context: ModuleContext,
) -> list[Violation]:
    """Validate test module structure and test functions."""

    violations: list[Violation] = []

    if not file_path.name.startswith(TEST_FUNCTION_PREFIX):
        violations.append(
            Violation(
                code="TC006",
                path=file_path,
                line=1,
                message="test file names must start with 'test_'",
            )
        )

    violations.extend(_check_top_level_test_module_shape(file_path=file_path, module=module))

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            TEST_FUNCTION_PREFIX
        ):
            violations.extend(
                _check_test_function(
                    file_path=file_path,
                    function_node=node,
                    local_test_types=local_test_types,
                    context=context,
                )
            )

    return violations


def _check_top_level_test_module_shape(*, file_path: Path, module: ast.Module) -> list[Violation]:
    if file_path.name == TEST_HELPERS_FILENAME:
        return []

    violations: list[Violation] = []
    first_test_function_line: int | None = None

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            TEST_FUNCTION_PREFIX
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
            and node.name.startswith(TEST_FUNCTION_PREFIX)
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
    *,
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

    parametrize: ast.expr | None = next(
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

    test_case_arg: ast.arg | None = next(
        (
            argument
            for argument in function_node.args.args
            if argument.arg == TEST_CASE_PARAMETER_NAME
        ),
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

    violations.extend(
        _check_parametrize_shape(
            file_path=file_path,
            function_node=function_node,
            decorator=parametrize,
            context=context,
        )
    )
    violations.extend(_check_no_if_statements(file_path=file_path, function_node=function_node))

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
    *,
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
    *,
    file_path: Path,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.Call,
    context: ModuleContext,
) -> list[Violation]:
    violations: list[Violation] = []

    parameter_and_values_argument_count: int = 2
    if len(decorator.args) < parameter_and_values_argument_count:
        return [
            Violation(
                code="TC012",
                path=file_path,
                line=function_node.lineno,
                message="@pytest.mark.parametrize must declare the parameter name and case values",
            )
        ]

    parameter_name: str | None = extract_name_constant(decorator.args[0])
    if parameter_name != TEST_CASE_PARAMETER_NAME:
        violations.append(
            Violation(
                code="TC013",
                path=file_path,
                line=function_node.lineno,
                message="@pytest.mark.parametrize must parameterize the 'test_case' argument",
            )
        )

    ids_expression: ast.expr | None = next(
        (keyword.value for keyword in decorator.keywords if keyword.arg == PARAMETRIZE_IDS_KEYWORD),
        None,
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

    values_expression: ast.expr = decorator.args[1]
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
        if not _is_local_test_case_constructor(expression=values_expression.elt, context=context):
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
        elif not _is_local_test_case_constructor(expression=element, context=context):
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
    test_case_field_chain_part_count: int = 2
    for node in ast.walk(function_node):
        if isinstance(node, ast.Attribute):
            chain: tuple[str, ...] | None = attribute_chain(node)
            if (
                chain
                and len(chain) >= test_case_field_chain_part_count
                and chain[0] == TEST_CASE_PARAMETER_NAME
                and chain[-1].startswith(EXPECTED_FIELD_PREFIX)
            ):
                return True
    return False


def _is_local_test_case_constructor(*, expression: ast.expr, context: ModuleContext) -> bool:
    if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name):
        return expression.func.id in context.imported_local_test_case_types
    return False


def _is_multi_case_list_name(name: str) -> bool:
    return name == TEST_CASE_COLLECTION_NAME or name.endswith(TEST_CASE_COLLECTION_SUFFIX)


def _is_description_lambda_ids(expression: ast.expr | None) -> bool:
    if not isinstance(expression, ast.Lambda):
        return False
    if len(expression.args.args) != 1:
        return False
    if expression.args.args[0].arg != DESCRIPTION_IDS_PARAMETER_NAME:
        return False
    return attribute_chain(expression.body) == (
        DESCRIPTION_IDS_PARAMETER_NAME,
        DESCRIPTION_FIELD_NAME,
    )
