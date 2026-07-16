"""Stable constants for test convention checks."""

import re

TEST_NAME_PATTERN: re.Pattern[str] = re.compile(r"^test_given_.+_when_.+_then_.+$")
VALID_TEST_SCOPES: frozenset[str] = frozenset({"unit", "integration", "e2e"})
DATACLASS_DECORATOR_NAME: str = "dataclass"
PYTEST_MARK_ATTRIBUTE_NAME: str = "mark"
PYTEST_PARAMETRIZE_ATTRIBUTE_NAME: str = "parametrize"
PYTHON_FILE_SUFFIX: str = ".py"
TEST_ROOT_DIRECTORY_NAME: str = "tests"
SOURCE_ROOT_DIRECTORY_NAME: str = "src"
TOOLING_ROOT_DIRECTORY_NAME: str = "scripts"
FILE_BACKED_TEST_AREAS: frozenset[tuple[str, str]] = frozenset({("sqlbuild", "providers")})
DESCRIPTION_FIELD_NAME: str = "description"
EXPECTED_FIELD_PREFIX: str = "expected_"
INIT_MODULE_FILENAME: str = "__init__.py"
TEST_TYPES_FILENAME: str = "_test_types.py"
SCENARIO_MODELS_FILENAME: str = "scenario_models.py"
TEST_HELPERS_FILENAME: str = "_test_helpers.py"
TEST_FUNCTION_PREFIX: str = "test_"
TEST_CASE_PARAMETER_NAME: str = "test_case"
PARAMETRIZE_IDS_KEYWORD: str = "ids"
TEST_CASE_COLLECTION_NAME: str = "TEST_CASES"
TEST_CASE_COLLECTION_SUFFIX: str = "_TEST_CASES"
DESCRIPTION_IDS_PARAMETER_NAME: str = "case"
