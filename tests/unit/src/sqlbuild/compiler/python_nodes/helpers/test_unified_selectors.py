"""Tests for unified SQL/Python selector helpers."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.helpers.unified_selectors import (
    resolve_python_sql_selectors,
    validate_python_sql_boundaries,
)
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlSelection
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers._test_types import (
    PythonSqlSelectorErrorTestCase,
    PythonSqlSelectorTestCase,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    build_model_depends_on_intermediate_loader_project_graph,
    build_orders_project_graph,
    build_orders_python_node_graph,
    build_python_node_graph_for_case,
    build_sql_downstream_task_to_loader_python_node_graph,
    build_sql_ref_python_node_graph,
    model_ref,
    source_ref,
)

PYTHON_SQL_SELECTOR_TEST_CASES: list[PythonSqlSelectorTestCase] = [
    PythonSqlSelectorTestCase(
        description="selects SQL resource by bare name",
        select=("orders",),
        exclude=(),
        expected_sql_names=frozenset({"orders"}),
        expected_python_node_names=frozenset(),
    ),
    PythonSqlSelectorTestCase(
        description="selects Python node by bare name",
        select=("prepare_orders",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects expanded Python node by typed selector",
        select=("+asset:export_orders",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects tag across SQL models and Python nodes",
        select=("tag:daily",),
        exclude=(),
        expected_sql_names=frozenset({"orders"}),
        expected_python_node_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects explicit models root path as SQL models",
        select=("path:models",),
        exclude=(),
        expected_sql_names=frozenset({"orders"}),
        expected_python_node_names=frozenset(),
    ),
    PythonSqlSelectorTestCase(
        description="selects explicit Python task path",
        select=("path:tasks",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects expanded explicit Python asset path",
        select=("+path:assets",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects expanded explicit Python asset slash path",
        select=("+assets/",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects expanded explicit Python asset leading slash path",
        select=("+/assets",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects expanded managed source by source identity",
        select=("+source:raw_orders",),
        exclude=(),
        expected_sql_names=frozenset({"raw_orders"}),
        expected_python_node_names=frozenset(),
    ),
    PythonSqlSelectorTestCase(
        description="selects source and intermediate loader without duplicate source names",
        select=("+source:raw_orders +loader:load_events",),
        exclude=(),
        expected_sql_names=frozenset({"raw_orders"}),
        expected_python_node_names=frozenset({"prepare_orders", "load_events"}),
    ),
    PythonSqlSelectorTestCase(
        description="excludes Python node from unified selection",
        select=("tag:daily",),
        exclude=("asset:export_orders",),
        expected_sql_names=frozenset({"orders"}),
        expected_python_node_names=frozenset({"prepare_orders"}),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_SELECTOR_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_SELECTOR_TEST_CASES],
)
def test_given_unified_selectors_when_resolving_then_returns_sql_and_python_selection(
    test_case: PythonSqlSelectorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_orders_python_node_graph()

    result: PythonSqlSelection = resolve_python_sql_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        project_graph=project_graph,
        python_graph=python_graph,
    )

    assert frozenset(key.name for key in result.sql_keys) == test_case.expected_sql_names
    assert result.python_node_names == test_case.expected_python_node_names


PYTHON_SQL_SELECTOR_ERROR_TEST_CASES: list[PythonSqlSelectorErrorTestCase] = [
    PythonSqlSelectorErrorTestCase(
        description="raises when selector matches no SQL resource or Python node",
        select=("missing",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="unknown selector name 'missing'",
    ),
    PythonSqlSelectorErrorTestCase(
        description="raises when path selector omits explicit root",
        select=("path:marts",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="path selectors require an explicit root",
    ),
    PythonSqlSelectorErrorTestCase(
        description="raises when slash path selector omits explicit root",
        select=("/marts",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="path selectors require an explicit root",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_SELECTOR_ERROR_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_SELECTOR_ERROR_TEST_CASES],
)
def test_given_unknown_unified_selector_when_resolving_then_raises_clear_error(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_orders_python_node_graph()

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_sql_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            project_graph=project_graph,
            python_graph=python_graph,
        )


PYTHON_SQL_REF_ERROR_TEST_CASES: list[PythonSqlSelectorErrorTestCase] = [
    PythonSqlSelectorErrorTestCase(
        description="raises when model ref is unknown",
        select=("profile_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="Python node 'profile_orders' depends on unknown SQL resource",
        sql_ref_dependency=model_ref("missing_orders"),
    ),
    PythonSqlSelectorErrorTestCase(
        description="raises when source ref names a model",
        select=("profile_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="declares source.*orders.*but.*orders.*is a model",
        sql_ref_dependency=source_ref("orders"),
    ),
    PythonSqlSelectorErrorTestCase(
        description="raises when model ref names a source",
        select=("profile_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="declares model.*raw_orders.*but.*raw_orders.*is a source",
        sql_ref_dependency=model_ref("raw_orders"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_REF_ERROR_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_REF_ERROR_TEST_CASES],
)
def test_given_invalid_typed_sql_ref_when_resolving_then_raises_clear_error(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    assert test_case.sql_ref_dependency is not None
    python_graph: PythonNodeGraph = build_sql_ref_python_node_graph(
        dependency=test_case.sql_ref_dependency
    )

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_sql_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            project_graph=project_graph,
            python_graph=python_graph,
        )


PYTHON_SQL_TERMINAL_LOADER_BOUNDARY_ERROR_TEST_CASES: list[PythonSqlSelectorErrorTestCase] = [
    PythonSqlSelectorErrorTestCase(
        description="raises when task depends on terminal source loader",
        select=("summarize_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment=(
            "Python node 'summarize_orders' depends on terminal loader 'raw_orders'; "
            "depend on source 'raw_orders' instead"
        ),
        python_graph_case="terminal_loader_task_dependency",
    ),
    PythonSqlSelectorErrorTestCase(
        description="raises when asset depends on terminal source loader",
        select=("export_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment=(
            "Python node 'export_orders' depends on terminal loader 'raw_orders'; "
            "depend on source 'raw_orders' instead"
        ),
        python_graph_case="terminal_loader_asset_dependency",
    ),
    PythonSqlSelectorErrorTestCase(
        description="raises when check depends on terminal source loader",
        select=("check_loaded_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment=(
            "Check 'check_loaded_orders' depends on terminal loader 'raw_orders'; "
            "use source audits for source 'raw_orders' instead"
        ),
        python_graph_case="terminal_loader_check_dependency",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_TERMINAL_LOADER_BOUNDARY_ERROR_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_TERMINAL_LOADER_BOUNDARY_ERROR_TEST_CASES],
)
def test_given_invalid_terminal_loader_dependency_when_validating_boundaries_then_raises(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_python_node_graph_for_case(test_case.python_graph_case)

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_sql_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            project_graph=project_graph,
            python_graph=python_graph,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonSqlSelectorErrorTestCase(
            description="raises when SQL model depends on intermediate loader",
            select=("orders",),
            exclude=(),
            expected_error_type=ValueError,
            expected_error_fragment=(
                "SQL model 'orders' depends on intermediate loader 'fetch_pages'; "
                "depend on a source populated by a terminal loader instead"
            ),
            python_graph_case="default",
        )
    ],
    ids=["raises when SQL model depends on intermediate loader"],
)
def test_given_invalid_sql_model_dependency_when_validating_boundaries_then_raises(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_model_depends_on_intermediate_loader_project_graph()
    python_graph: PythonNodeGraph = build_python_node_graph_for_case(test_case.python_graph_case)

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_sql_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            project_graph=project_graph,
            python_graph=python_graph,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonSqlSelectorErrorTestCase(
            description="raises when SQL downstream task feeds loader",
            select=("load_events",),
            exclude=(),
            expected_error_type=ValueError,
            expected_error_fragment=(
                "Loader 'load_events' depends on Python node 'prepare_orders' which depends on SQL"
            ),
        )
    ],
    ids=["raises when SQL downstream task feeds loader"],
)
def test_given_sql_downstream_task_feeds_loader_when_validating_then_raises(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_sql_downstream_task_to_loader_python_node_graph()

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_sql_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            project_graph=project_graph,
            python_graph=python_graph,
        )


PYTHON_SQL_INTERMEDIATE_LOADER_BOUNDARY_TEST_CASES: list[PythonSqlSelectorErrorTestCase] = [
    PythonSqlSelectorErrorTestCase(
        description="allows task dependency on intermediate loader",
        select=("summarize_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment=None,
        python_graph_case="intermediate_loader_task_dependency",
    ),
    PythonSqlSelectorErrorTestCase(
        description="allows asset dependency on intermediate loader",
        select=("export_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment=None,
        python_graph_case="intermediate_loader_asset_dependency",
    ),
    PythonSqlSelectorErrorTestCase(
        description="allows check dependency on intermediate loader",
        select=("check_loaded_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment=None,
        python_graph_case="intermediate_loader_check_dependency",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_INTERMEDIATE_LOADER_BOUNDARY_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_INTERMEDIATE_LOADER_BOUNDARY_TEST_CASES],
)
def test_given_intermediate_loader_dependency_when_validating_boundaries_then_it_is_allowed(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_python_node_graph_for_case(test_case.python_graph_case)

    validate_python_sql_boundaries(project_graph=project_graph, python_graph=python_graph)
    assert test_case.expected_error_fragment is None
