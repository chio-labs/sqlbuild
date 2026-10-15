from __future__ import annotations

import pytest

from sqlbuild._native import CliNamespace, CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from tests.unit.src.sqlbuild.cli.commands.classes._test_types import (
    CliNamespaceAssignmentTestCase,
    CliNamespaceDefaultTestCase,
    CliNamespaceListIsolationTestCase,
    CliNamespaceMissingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliNamespaceDefaultTestCase(
            description="an unset option is None",
            attribute="project_dir",
            expected_value=None,
        ),
        CliNamespaceDefaultTestCase(
            description="a flag defaults to False",
            attribute="dry_run",
            expected_value=False,
        ),
        CliNamespaceDefaultTestCase(
            description="an enabled-by-default flag is True",
            attribute="run_tests",
            expected_value=True,
        ),
        CliNamespaceDefaultTestCase(
            description="an integer option keeps its default",
            attribute="query_limit",
            expected_value=20,
        ),
        CliNamespaceDefaultTestCase(
            description="a text option keeps its default",
            attribute="playground_template",
            expected_value="waffle_shop",
        ),
        CliNamespaceDefaultTestCase(
            description="compile lineage defaults to the fast mode",
            attribute="compile_lineage_mode",
            expected_value=CompileLineageMode.FAST,
        ),
        CliNamespaceDefaultTestCase(
            description="column lineage defaults to the rich mode",
            attribute="lineage_mode",
            expected_value=ColumnLineageMode.RICH,
        ),
        CliNamespaceDefaultTestCase(
            description="CLI vars default to an empty mapping",
            attribute="vars",
            expected_value={},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_new_namespace_when_reading_option_then_returns_its_default(
    test_case: CliNamespaceDefaultTestCase,
) -> None:
    namespace: CliNamespace = CliNamespace()

    assert getattr(namespace, test_case.attribute) == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        CliNamespaceListIsolationTestCase(
            description="selectors appended to one namespace stay out of another",
            attribute="select",
            appended_value="orders",
            expected_first=["orders"],
            expected_second=[],
        ),
        CliNamespaceListIsolationTestCase(
            description="excludes appended to one namespace stay out of another",
            attribute="exclude",
            appended_value="customers",
            expected_first=["customers"],
            expected_second=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_namespaces_when_extending_a_list_default_then_the_other_is_unchanged(
    test_case: CliNamespaceListIsolationTestCase,
) -> None:
    first: CliNamespace = CliNamespace()
    second: CliNamespace = CliNamespace()

    getattr(first, test_case.attribute).append(test_case.appended_value)

    assert getattr(first, test_case.attribute) == test_case.expected_first
    assert getattr(second, test_case.attribute) == test_case.expected_second


@pytest.mark.parametrize(
    "test_case",
    [
        CliNamespaceAssignmentTestCase(
            description="an assigned option overrides its default",
            attribute="command",
            value="build",
            expected_value="build",
        ),
        CliNamespaceAssignmentTestCase(
            description="an option without a default can be assigned",
            attribute="event_output",
            value=None,
            expected_value=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_namespace_when_assigning_then_attribute_holds_the_value(
    test_case: CliNamespaceAssignmentTestCase,
) -> None:
    namespace: CliNamespace = CliNamespace()

    setattr(namespace, test_case.attribute, test_case.value)

    assert getattr(namespace, test_case.attribute) == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        CliNamespaceMissingTestCase(
            description="an option without a default is missing until assigned",
            attribute="event_output",
            expected_error_fragment="'CliNamespace' object has no attribute 'event_output'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_namespace_when_reading_undeclared_default_then_raises_attribute_error(
    test_case: CliNamespaceMissingTestCase,
) -> None:
    namespace: CliNamespace = CliNamespace()

    with pytest.raises(AttributeError, match=test_case.expected_error_fragment):
        getattr(namespace, test_case.attribute)
