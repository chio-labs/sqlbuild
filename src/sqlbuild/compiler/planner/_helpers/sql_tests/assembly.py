"""SQL-native unit-test plan entries built from native chain planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.constants import (
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    TABLE_FN_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.planner._helpers.fixtures.completion import build_relation_fixture_context
from sqlbuild.compiler.planner._helpers.sql_tests.fixture_validation import (
    build_validated_test_fixtures,
    fixture_location,
)
from sqlbuild.compiler.planner._helpers.sql_tests.native_planning import (
    plan_sql_tests_natively,
    resolve_sql_test_model_chains,
    sql_test_plan_error_messages,
)
from sqlbuild.compiler.planner.exceptions import SqlTestFixtureValidationError
from sqlbuild.compiler.planner.models import (
    NativeSqlTestPlan,
    RelationFixturePlanningContext,
    SqlTestPlanEntry,
    SqlTestPlanResult,
)
from sqlbuild.executor.testing.main.missing_expected_columns import (
    describe_missing_expected_columns,
)

_FUNCTION_RESOURCE_TYPES: frozenset[CompiledResourceType] = frozenset(
    {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}
)


def plan_sql_tests(
    *,
    tests: tuple[CompiledSqlTest, ...],
    project: CompiledProject,
    adapter: BaseAdapter,
    sql_analysis_enabled: bool = False,
    validate_fixtures: bool = False,
    fixture_planning_context: RelationFixturePlanningContext | None = None,
) -> tuple[SqlTestPlanResult, ...]:
    """Plan SQL tests in one native batch, reporting fixture diagnostics per test."""

    planned_tests: tuple[CompiledSqlTest, ...] = tests
    diagnostics_by_index: dict[int, tuple[str, ...]] = {}
    validation_context: RelationFixturePlanningContext | None = None
    if sql_analysis_enabled and validate_fixtures:
        validation_context = fixture_planning_context or build_relation_fixture_context(
            project=project
        )
        planned_tests, diagnostics_by_index = _validate_fixtures(
            tests=tests,
            project=project,
            adapter=adapter,
            fixture_planning_context=validation_context,
        )
    plannable_indexes: tuple[int, ...] = tuple(
        index for index in range(len(tests)) if index not in diagnostics_by_index
    )
    plans: tuple[NativeSqlTestPlan, ...] = plan_sql_tests_natively(
        project=project,
        tests=tuple(planned_tests[index] for index in plannable_indexes),
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
        render_sql=False,
    )
    plans_by_index: dict[int, NativeSqlTestPlan] = dict(zip(plannable_indexes, plans, strict=True))
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    results: list[SqlTestPlanResult] = []
    for index, test in enumerate(tests):
        plan: NativeSqlTestPlan | None = plans_by_index.get(index)
        if plan is None:
            results.append(
                SqlTestPlanResult(entry=None, fixture_diagnostics=diagnostics_by_index[index])
            )
            continue
        plan_diagnostics: tuple[str, ...] = (
            *sql_test_plan_error_messages(warnings=plan.warnings),
            *_expected_column_diagnostics(
                test=test, plan=plan, fixture_planning_context=validation_context
            ),
        )
        if plan_diagnostics:
            results.append(SqlTestPlanResult(entry=None, fixture_diagnostics=plan_diagnostics))
            continue
        results.append(
            SqlTestPlanResult(
                entry=_plan_entry(
                    test=test,
                    plan=plan,
                    project=project,
                    models_by_name=models_by_name,
                    sql_analysis_enabled=sql_analysis_enabled,
                ),
                warnings=plan.warnings,
            )
        )
    return tuple(results)


def _expected_column_diagnostics(
    *,
    test: CompiledSqlTest,
    plan: NativeSqlTestPlan,
    fixture_planning_context: RelationFixturePlanningContext | None,
) -> tuple[str, ...]:
    """Report expected columns that authoritative model output metadata proves absent."""

    if fixture_planning_context is None:
        return ()
    diagnostics: list[str] = []
    for step in plan.chain:
        available_columns: frozenset[str] | None = (
            fixture_planning_context.authoritative_columns.get(
                (CompiledResourceType.MODEL, step.model_name)
            )
        )
        if step.expected_columns is None or available_columns is None:
            continue
        message: str | None = describe_missing_expected_columns(
            model_name=step.model_name,
            expected_columns=step.expected_columns,
            available_columns=available_columns,
        )
        if message is None:
            continue
        location: str = fixture_location(
            test=test, resource_type=CompiledResourceType.SQL_TEST, name=step.model_name
        )
        diagnostics.append(f"SQL test '{test.name}': {location}: {message}")
    return tuple(diagnostics)


def _validate_fixtures(
    *,
    tests: tuple[CompiledSqlTest, ...],
    project: CompiledProject,
    adapter: BaseAdapter,
    fixture_planning_context: RelationFixturePlanningContext,
) -> tuple[tuple[CompiledSqlTest, ...], dict[int, tuple[str, ...]]]:
    """Return tests with validated fixture completions plus diagnostics by test index."""

    model_indexes: tuple[int, ...] = tuple(
        index
        for index, test in enumerate(tests)
        if isinstance(test.payload, CompiledModelSqlTestPayload)
    )
    if not model_indexes:
        return tests, {}
    chains: tuple[tuple[str, ...], ...] = resolve_sql_test_model_chains(
        project=project,
        tests=tuple(tests[index] for index in model_indexes),
    )
    chains_by_index: dict[int, tuple[str, ...]] = dict(zip(model_indexes, chains, strict=True))
    context: RelationFixturePlanningContext = fixture_planning_context
    validated_tests: list[CompiledSqlTest] = []
    diagnostics_by_index: dict[int, tuple[str, ...]] = {}
    for index, test in enumerate(tests):
        chain: tuple[str, ...] | None = chains_by_index.get(index)
        if chain is None:
            validated_tests.append(test)
            continue
        try:
            validated_tests.append(
                _with_validated_fixtures(
                    test=test,
                    project=project,
                    adapter=adapter,
                    ordered_model_names=chain,
                    fixture_planning_context=context,
                )
            )
        except SqlTestFixtureValidationError as error:
            validated_tests.append(test)
            diagnostics_by_index[index] = error.diagnostics
    return tuple(validated_tests), diagnostics_by_index


def _with_validated_fixtures(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    ordered_model_names: tuple[str, ...],
    fixture_planning_context: RelationFixturePlanningContext,
) -> CompiledSqlTest:
    payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = test.payload
    if not isinstance(payload, CompiledModelSqlTestPayload):
        return test
    mock_refs, mock_sources, mock_seeds, expected_outputs = build_validated_test_fixtures(
        test=test,
        project=project,
        adapter=adapter,
        ordered_model_names=ordered_model_names,
        mock_refs=_prefixed_ctes(ctes=payload.authored_ctes, prefix=REF_TEST_CTE_PREFIX),
        mock_sources=_prefixed_ctes(ctes=payload.authored_ctes, prefix=SOURCE_TEST_CTE_PREFIX),
        mock_seeds=_prefixed_ctes(ctes=payload.authored_ctes, prefix=SEED_TEST_CTE_PREFIX),
        expected_outputs=_expected_outputs(payload=payload),
        planning_context=fixture_planning_context,
    )
    completed_bodies: tuple[tuple[str, dict[str, str]], ...] = (
        (REF_TEST_CTE_PREFIX, mock_refs),
        (SOURCE_TEST_CTE_PREFIX, mock_sources),
        (SEED_TEST_CTE_PREFIX, mock_seeds),
    )
    authored_ctes: tuple[CompileSqlTestCte, ...] = tuple(
        _completed_cte(cte=cte, completed_bodies=completed_bodies) for cte in payload.authored_ctes
    )
    expected_ctes: tuple[CompileSqlTestCte, ...] = tuple(
        replace(
            cte,
            sql_body=expected_outputs.get(
                cte.name.removeprefix(EXPECTED_TEST_CTE_PREFIX), cte.sql_body
            ),
        )
        for cte in payload.expected_ctes
    )
    return replace(
        test,
        payload=replace(payload, authored_ctes=authored_ctes, expected_ctes=expected_ctes),
    )


def _completed_cte(
    *,
    cte: CompileSqlTestCte,
    completed_bodies: tuple[tuple[str, dict[str, str]], ...],
) -> CompileSqlTestCte:
    for prefix, bodies in completed_bodies:
        if cte.name.startswith(prefix):
            return replace(cte, sql_body=bodies.get(cte.name.removeprefix(prefix), cte.sql_body))
    return cte


def _expected_outputs(*, payload: CompiledModelSqlTestPayload) -> dict[str, str]:
    return {
        cte.name.removeprefix(EXPECTED_TEST_CTE_PREFIX): cte.sql_body
        for cte in payload.expected_ctes
    }


def _prefixed_ctes(*, ctes: tuple[CompileSqlTestCte, ...], prefix: str) -> dict[str, str]:
    return {
        cte.name.removeprefix(prefix): cte.sql_body for cte in ctes if cte.name.startswith(prefix)
    }


def _prefixed_names(*, test: CompiledSqlTest, prefix: str) -> tuple[str, ...]:
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return ()
    return tuple(sorted(_prefixed_ctes(ctes=test.payload.authored_ctes, prefix=prefix)))


def _plan_entry(
    *,
    test: CompiledSqlTest,
    plan: NativeSqlTestPlan,
    project: CompiledProject,
    models_by_name: dict[str, CompiledModel],
    sql_analysis_enabled: bool,
) -> SqlTestPlanEntry:
    mock_table_function_names: tuple[str, ...] = _prefixed_names(
        test=test, prefix=TABLE_FN_TEST_CTE_PREFIX
    )
    return SqlTestPlanEntry(
        key=test.key,
        name=test.name,
        source_path=test.source_path,
        block_index=test.block_index,
        parent_name=test.parent_name,
        case_name=test.case_name,
        case_index=test.case_index,
        case_fingerprint=test.case_fingerprint,
        parameter_schema=test.parameter_schema,
        parameter_values=test.parameter_values,
        mock_ref_names=_prefixed_names(test=test, prefix=REF_TEST_CTE_PREFIX),
        mock_source_names=_prefixed_names(test=test, prefix=SOURCE_TEST_CTE_PREFIX),
        mock_seed_names=_prefixed_names(test=test, prefix=SEED_TEST_CTE_PREFIX),
        mock_dbt_ref_names=_prefixed_names(test=test, prefix=DBT_REF_TEST_CTE_PREFIX),
        mock_table_function_names=mock_table_function_names,
        chain=plan.chain,
        assertions=plan.assertions,
        scope_deps=test.scope_deps,
        function_deps=(
            _direct_function_deps(test=test, project=project)
            if isinstance(test.payload, CompiledDirectLogicSqlTestPayload)
            else _chain_function_deps(
                model_names=plan.model_names,
                models_by_name=models_by_name,
                mocked_table_functions=frozenset(mock_table_function_names),
            )
        ),
        sql_analysis_enabled=sql_analysis_enabled,
    )


def _chain_function_deps(
    *,
    model_names: tuple[str, ...],
    models_by_name: dict[str, CompiledModel],
    mocked_table_functions: frozenset[str],
) -> tuple[CompiledObjectKey, ...]:
    deps: dict[CompiledObjectKey, None] = {}
    for model_name in model_names:
        model: CompiledModel | None = models_by_name.get(model_name)
        if model is None:
            continue
        for dep in model.deps:
            if dep.resource_type not in _FUNCTION_RESOURCE_TYPES:
                continue
            if dep.resource_type == CompiledResourceType.TABLE_FN and (
                dep.name in mocked_table_functions
            ):
                continue
            deps[dep] = None
    return tuple(deps)


def _direct_function_deps(
    *, test: CompiledSqlTest, project: CompiledProject
) -> tuple[CompiledObjectKey, ...]:
    if not isinstance(test.payload, CompiledDirectLogicSqlTestPayload):
        return ()
    resource_type: CompiledResourceType | None = {
        SqlTestMode.UDF: CompiledResourceType.UDF,
        SqlTestMode.TABLE_FN: CompiledResourceType.TABLE_FN,
    }.get(test.payload.mode)
    if resource_type is None:
        return ()
    tested_names: frozenset[str] = frozenset(test.payload.tested_resource_names)
    return tuple(
        function.key
        for function in project.functions
        if function.key.resource_type == resource_type and function.name in tested_names
    )
