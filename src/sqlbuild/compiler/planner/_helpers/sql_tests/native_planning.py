"""Native SQL-test chain planning and comparison rendering boundary."""

from __future__ import annotations

import time
from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.classes.sql_test_cte_locator import SqlTestCteLocator
from sqlbuild.compiler.compile.constants import SQL_TEST_HELPER_REFERENCE_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError, SqlTestReferenceError
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.planner._helpers.sql_tests.cursor_window import (
    declared_window_cursor_models,
    declares_cursor_window,
    render_test_cursor_intrinsics,
)
from sqlbuild.compiler.planner.exceptions import NativeSqlTestPlanningError, PlannerInputError
from sqlbuild.compiler.planner.models import (
    ChainStep,
    NativeSqlTestArtifact,
    NativeSqlTestPlan,
    PlanWarning,
    SqlTestAssertionStep,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.compiler.sql_test_glue.constants import CURSOR_INTRINSIC_NAMES
from sqlbuild.compiler.sql_test_glue.models import (
    NativeSqlTestChainRequest,
    NativeSqlTestPlanningRequest,
)
from sqlbuild.compiler.sql_test_glue.types import (
    NativeAssertionStepRow,
    NativeChainStepRow,
    NativeSqlTestPlanRow,
)
from sqlbuild.executor.testing.types import NativeSqlTestRenderingModule

_UNRESOLVED_REFERENCE_PREFIX: str = "sql_test_reference:"

_CALL_SUFFIX_SENTINEL: str = "__SQLBUILD_CALL_SUFFIX__"
_NATIVE_WORKERS: int = 4


def plan_and_render_sql_test_artifacts(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[NativeSqlTestArtifact, ...]:
    """Plan and render SQL tests in one deterministic native project call."""

    artifacts: list[NativeSqlTestArtifact] = []
    for plan in _plan_sql_tests_from_json(
        project=project,
        tests=tests,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
        render_sql=True,
        include_plan=False,
    ):
        if plan.sql is None:
            raise NativeSqlTestPlanningError("native SQL-test planning omitted rendered SQL")
        artifacts.append(
            NativeSqlTestArtifact(
                sql=plan.sql,
                model_names=plan.model_names,
                error_messages=plan.error_messages,
            )
        )
    return tuple(artifacts)


def plan_compiled_sql_test_artifacts(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[NativeSqlTestArtifact, ...]:
    """Plan and render SQL tests from the compiled objects, with natively projected errors."""

    artifacts: list[NativeSqlTestArtifact] = []
    for plan in _plan_compiled_sql_tests(
        project=project,
        tests=tests,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
        render_sql=True,
        include_plan=False,
    ):
        if plan.sql is None:
            raise NativeSqlTestPlanningError("native SQL-test planning omitted rendered SQL")
        artifacts.append(
            NativeSqlTestArtifact(
                sql=plan.sql, model_names=plan.model_names, error_messages=plan.error_messages
            )
        )
    return tuple(artifacts)


def sql_test_plan_error_messages(*, warnings: tuple[PlanWarning, ...]) -> tuple[str, ...]:
    """Return each distinct ERROR-severity planning message for one SQL test, in order."""

    return tuple(
        dict.fromkeys(
            warning.message for warning in warnings if warning.severity is WarningSeverity.ERROR
        )
    )


def plan_sql_tests_natively(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
    render_sql: bool,
    include_plan: bool = True,
) -> tuple[NativeSqlTestPlan, ...]:
    """Plan SQL-test chains and assertions in one native batch, optionally rendering SQL."""

    if native_stage_enabled(NativeStage.SQL_TEST_GLUE):
        return _plan_compiled_sql_tests(
            project=project,
            tests=tests,
            adapter=adapter,
            sql_analysis_enabled=sql_analysis_enabled,
            render_sql=render_sql,
            include_plan=include_plan,
        )
    return _plan_sql_tests_from_json(
        project=project,
        tests=tests,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
        render_sql=render_sql,
        include_plan=include_plan,
    )


def _plan_compiled_sql_tests(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
    render_sql: bool,
    include_plan: bool,
) -> tuple[NativeSqlTestPlan, ...]:
    """Plan from the compiled objects natively; Python supplies only the adapter's renderings."""

    if not tests:
        return ()
    start_ns: int = time.perf_counter_ns()
    rendered_model_sql: dict[int, str] = {
        index: render_test_cursor_intrinsics(
            sql=model.query_sql, model=model, adapter=adapter, test=None
        )
        for index, model in enumerate(project.models)
        if _mentions_cursor_intrinsic(model.query_sql)
    }
    functions: tuple[tuple[str, str, str, str, str], ...] = _function_templates(
        project=project, adapter=adapter
    )
    rendered_test_overrides: dict[int, dict[str, str]] = _rendered_test_overrides(
        project=project, tests=tests, adapter=adapter
    )
    request: NativeSqlTestPlanningRequest = NativeSqlTestPlanningRequest(
        models=project.models,
        rendered_model_sql=rendered_model_sql,
        functions=functions,
        tests=tests,
        rendered_test_overrides=rendered_test_overrides,
        sql_analysis_enabled=sql_analysis_enabled,
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
        set_difference_operator=adapter.render_set_difference_operator(),
        requires_derived_table_aliases=adapter.requires_derived_table_aliases(),
        lexical_syntax=project.sql_lexical_syntax.native_mapping,
        render_sql=render_sql,
        include_plan=include_plan,
    )
    try:
        rows, planning_ns, rendering_ns = _native.plan_compiled_sql_tests(request)
    except ValueError as error:
        raise _planning_error(error=error, tests=tests) from None
    _record_planning_timing(start_ns=start_ns, planning_ns=planning_ns, rendering_ns=rendering_ns)
    return tuple(_plan_from_row(row=row) for row in rows)


def _plan_from_row(*, row: NativeSqlTestPlanRow) -> NativeSqlTestPlan:
    sql, chain, assertions, model_names, warnings, error_messages = row
    return NativeSqlTestPlan(
        chain=tuple(_chain_step_from_row(row=step) for step in chain),
        assertions=tuple(_assertion_step_from_row(row=step) for step in assertions),
        model_names=tuple(model_names),
        warnings=tuple(
            PlanWarning(model_name=model_name, severity=WarningSeverity(severity), message=message)
            for model_name, severity, message in warnings
        ),
        error_messages=tuple(error_messages),
        sql=sql,
    )


def _assertion_step_from_row(*, row: NativeAssertionStepRow) -> SqlTestAssertionStep:
    name, resolved_sql, lifted_ctes, comparison_body_sql = row
    return SqlTestAssertionStep(
        name=name,
        resolved_sql=resolved_sql,
        lifted_ctes=tuple(lifted_ctes),
        comparison_body_sql=comparison_body_sql,
    )


def _chain_step_from_row(*, row: NativeChainStepRow) -> ChainStep:
    (
        model_name,
        resolved_sql,
        expected_cte_sql,
        lifted_ctes,
        comparison_body_sql,
        expected_columns,
        expected_lifted_ctes,
    ) = row
    return ChainStep(
        model_name=model_name,
        resolved_sql=resolved_sql,
        expected_cte_sql=expected_cte_sql,
        lifted_ctes=tuple(lifted_ctes),
        comparison_body_sql=comparison_body_sql,
        expected_columns=None if expected_columns is None else tuple(expected_columns),
        expected_lifted_ctes=tuple(expected_lifted_ctes),
    )


def _mentions_cursor_intrinsic(sql: str) -> bool:
    """Whether SQL names a cursor intrinsic; SQL that does not is never rendered differently."""

    return any(name in sql for name in CURSOR_INTRINSIC_NAMES)


def _rendered_test_overrides(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...], adapter: BaseAdapter
) -> dict[int, dict[str, str]]:
    """Cursor-rendered model overrides for the tests whose overrides cursor windows change."""

    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    windowed_indexes: tuple[int, ...] = tuple(
        index
        for index, test in enumerate(tests)
        if isinstance(test.payload, CompiledModelSqlTestPayload)
        and declares_cursor_window(test=test)
    )
    chains: tuple[tuple[str, ...], ...] = (
        resolve_sql_test_model_chains(
            project=project, tests=tuple(tests[index] for index in windowed_indexes)
        )
        if windowed_indexes
        else ()
    )
    chains_by_index: dict[int, tuple[str, ...]] = dict(zip(windowed_indexes, chains, strict=True))
    rendered: dict[int, dict[str, str]] = {}
    for index, test in enumerate(tests):
        payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = test.payload
        if not isinstance(payload, CompiledModelSqlTestPayload):
            continue
        chain: tuple[str, ...] | None = chains_by_index.get(index)
        if chain is None and not any(
            _mentions_cursor_intrinsic(sql) for sql in payload.model_query_overrides.values()
        ):
            continue
        overrides: dict[str, str] | None = _windowed_model_query_overrides(
            test=test, models_by_name=models_by_name, adapter=adapter, chain=chain
        )
        if overrides is not None:
            rendered[index] = overrides
    return rendered


def _record_planning_timing(*, start_ns: int, planning_ns: int, rendering_ns: int) -> None:
    elapsed_ns: int = time.perf_counter_ns() - start_ns
    boundary_overhead_ns: int = max(0, elapsed_ns - planning_ns - rendering_ns)
    collector: CompileTimingCollector | None = CompileTimingContext.active.get()
    if collector is not None:
        collector.add(
            phase="test_planning_ms",
            elapsed_ns=planning_ns + boundary_overhead_ns,
        )
        collector.add(phase="comparison_render_ms", elapsed_ns=rendering_ns)


def _plan_sql_tests_from_json(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
    render_sql: bool,
    include_plan: bool,
) -> tuple[NativeSqlTestPlan, ...]:
    if not tests:
        return ()
    start_ns: int = time.perf_counter_ns()
    request: dict[str, object] = {
        "models": _model_requests(project=project, adapter=adapter),
        "functions": _function_requests(project=project, adapter=adapter),
        "tests": _planning_test_requests(project=project, tests=tests, adapter=adapter),
        "sqlAnalysisEnabled": sql_analysis_enabled,
        "sqlAnalysisDialect": adapter.sql_analysis_dialect(),
        "setDifferenceOperator": adapter.render_set_difference_operator(),
        "requiresDerivedTableAliases": adapter.requires_derived_table_aliases(),
        "lexicalSyntax": _lexical_syntax_request(project.sql_lexical_syntax),
        "workers": _NATIVE_WORKERS,
        "renderSql": render_sql,
        "includePlan": include_plan,
    }
    try:
        native_response: str = cast(
            NativeSqlTestRenderingModule, _native
        ).plan_and_render_sql_tests_json(
            orjson.dumps(request, option=orjson.OPT_SORT_KEYS).decode()
        )
    except ValueError as error:
        raise _planning_error(error=error, tests=tests) from None
    response_payload: object = orjson.loads(native_response)
    if not isinstance(response_payload, dict):
        raise NativeSqlTestPlanningError(
            "native SQL-test planning returned an invalid batch response"
        )
    response: object = response_payload.get("artifacts")
    planning_ns: object = response_payload.get("planningNs")
    rendering_ns: object = response_payload.get("renderingNs")
    if (
        not isinstance(response, list)
        or len(response) != len(tests)
        or not isinstance(planning_ns, int)
        or isinstance(planning_ns, bool)
        or not isinstance(rendering_ns, int)
        or isinstance(rendering_ns, bool)
    ):
        raise NativeSqlTestPlanningError(
            "native SQL-test planning returned an invalid batch response"
        )
    plans: tuple[NativeSqlTestPlan, ...] = tuple(
        _plan_from_payload(value=value) for value in response
    )
    _record_planning_timing(start_ns=start_ns, planning_ns=planning_ns, rendering_ns=rendering_ns)
    return plans


def resolve_sql_test_model_chains(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...]
) -> tuple[tuple[str, ...], ...]:
    """Return each test's ordered unmocked model chain; direct-logic tests have none."""

    if not tests:
        return ()
    if native_stage_enabled(NativeStage.SQL_TEST_GLUE):
        try:
            native_chains: list[list[str]] = _native.resolve_compiled_sql_test_chains(
                NativeSqlTestChainRequest(
                    models=project.models,
                    tests=tests,
                    lexical_syntax=project.sql_lexical_syntax.native_mapping,
                )
            )
        except ValueError as error:
            raise _planning_error(error=error, tests=tests) from None
        return tuple(tuple(chain) for chain in native_chains)
    request: dict[str, object] = {
        "models": _chain_model_requests(project=project),
        "tests": [_test_request(test=test) for test in tests],
        "lexicalSyntax": _lexical_syntax_request(project.sql_lexical_syntax),
    }
    try:
        native_response: str = cast(
            NativeSqlTestRenderingModule, _native
        ).resolve_sql_test_chains_json(orjson.dumps(request, option=orjson.OPT_SORT_KEYS).decode())
    except ValueError as error:
        raise _planning_error(error=error, tests=tests) from None
    response_payload: object = orjson.loads(native_response)
    chains: object = response_payload.get("chains") if isinstance(response_payload, dict) else None
    if not isinstance(chains, list) or len(chains) != len(tests):
        raise NativeSqlTestPlanningError(
            "native SQL-test chain resolution returned an invalid response"
        )
    return tuple(_string_tuple(value=chain, context="chain") for chain in chains)


def _planning_error(*, error: ValueError, tests: tuple[CompiledSqlTest, ...]) -> Exception:
    message: str = str(error)
    if message.startswith(_UNRESOLVED_REFERENCE_PREFIX):
        return _unresolved_reference_error(
            payload=orjson.loads(message.removeprefix(_UNRESOLVED_REFERENCE_PREFIX)), tests=tests
        )
    if message.startswith("compile_input:"):
        return CompileInputError(message.removeprefix("compile_input:"))
    if message.startswith("planner_input:"):
        return PlannerInputError(message.removeprefix("planner_input:"))
    return NativeSqlTestPlanningError(f"native SQL-test planning failed: {message}")


def _unresolved_reference_error(
    *, payload: dict[str, str], tests: tuple[CompiledSqlTest, ...]
) -> Exception:
    """Locate a reference call the native planner could not resolve in its test file."""

    test: CompiledSqlTest | None = next(
        (
            test
            for test in tests
            if test.name == payload["testName"]
            and str(test.test_file.relative_path) == payload["fileLabel"]
        ),
        None,
    )
    cte_name: str = payload["cteName"]
    call: str = payload["call"]
    message: str = f"SQL test CTE '{cte_name}' calls {call}, which the test query cannot resolve"
    help_text: str = (
        f"Mock it in the test, for example {payload['mockCte']} AS (SELECT ...), or call "
        '__ref("<model>") on a model the test runs.'
    )
    if test is None:
        return CompileInputError(message, code=SQL_TEST_HELPER_REFERENCE_CODE, help=help_text)
    return SqlTestReferenceError(
        message,
        location=SqlTestCteLocator.locate(
            test_file=test.test_file, test_block=test.test_block, cte_name=cte_name, call=call
        ),
        help=help_text,
    )


def _plan_from_payload(*, value: object) -> NativeSqlTestPlan:
    payload: dict[str, Any] = _object(value=value, context="result")
    sql: object = payload.get("sql")
    chain: object = payload.get("chain")
    assertions: object = payload.get("assertions")
    warnings: object = payload.get("warnings")
    if (
        (sql is not None and not isinstance(sql, str))
        or not isinstance(chain, list)
        or not isinstance(assertions, list)
        or not isinstance(warnings, list)
    ):
        raise NativeSqlTestPlanningError("native SQL-test planning returned an invalid result")
    plan_warnings: tuple[PlanWarning, ...] = tuple(_warning(value=warning) for warning in warnings)
    return NativeSqlTestPlan(
        chain=tuple(_chain_step(value=step) for step in chain),
        assertions=tuple(_assertion_step(value=step) for step in assertions),
        model_names=_string_tuple(value=payload.get("modelNames"), context="model names"),
        warnings=plan_warnings,
        error_messages=sql_test_plan_error_messages(warnings=plan_warnings),
        sql=sql if isinstance(sql, str) else None,
    )


def _chain_step(*, value: object) -> ChainStep:
    payload: dict[str, Any] = _object(value=value, context="chain step")
    return ChainStep(
        model_name=_string(value=payload.get("modelName"), context="chain step model"),
        resolved_sql=_string(value=payload.get("resolvedSql"), context="chain step SQL"),
        expected_cte_sql=_optional_string(
            value=payload.get("expectedCteSql"), context="chain step expected SQL"
        ),
        lifted_ctes=_cte_pairs(value=payload.get("liftedCtes")),
        comparison_body_sql=_optional_string(
            value=payload.get("comparisonBodySql"), context="chain step comparison SQL"
        ),
        expected_columns=_optional_string_tuple(
            value=payload.get("expectedColumns"), context="chain step expected columns"
        ),
        expected_lifted_ctes=_cte_pairs(value=payload.get("expectedLiftedCtes", [])),
    )


def _assertion_step(*, value: object) -> SqlTestAssertionStep:
    payload: dict[str, Any] = _object(value=value, context="assertion step")
    return SqlTestAssertionStep(
        name=_string(value=payload.get("name"), context="assertion name"),
        resolved_sql=_string(value=payload.get("resolvedSql"), context="assertion SQL"),
        lifted_ctes=_cte_pairs(value=payload.get("liftedCtes")),
        comparison_body_sql=_optional_string(
            value=payload.get("comparisonBodySql"), context="assertion comparison SQL"
        ),
    )


def _warning(*, value: object) -> PlanWarning:
    payload: dict[str, Any] = _object(value=value, context="warning")
    return PlanWarning(
        model_name=_optional_string(value=payload.get("modelName"), context="warning model"),
        severity=WarningSeverity(
            _string(value=payload.get("severity"), context="warning severity")
        ),
        message=_string(value=payload.get("message"), context="warning message"),
    )


def _cte_pairs(*, value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise NativeSqlTestPlanningError("native SQL-test planning returned invalid lifted CTEs")
    pairs: list[tuple[str, str]] = []
    for pair in value:
        name, sql = _string_tuple(value=pair, context="lifted CTE")
        pairs.append((name, sql))
    return tuple(pairs)


def _object(*, value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NativeSqlTestPlanningError(f"native SQL-test planning returned an invalid {context}")
    return cast(dict[str, Any], value)


def _string(*, value: object, context: str) -> str:
    if not isinstance(value, str):
        raise NativeSqlTestPlanningError(f"native SQL-test planning returned an invalid {context}")
    return value


def _optional_string(*, value: object, context: str) -> str | None:
    return None if value is None else _string(value=value, context=context)


def _optional_string_tuple(*, value: object, context: str) -> tuple[str, ...] | None:
    return None if value is None else _string_tuple(value=value, context=context)


def _string_tuple(*, value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise NativeSqlTestPlanningError(f"native SQL-test planning returned an invalid {context}")
    return tuple(_string(value=item, context=context) for item in value)


def _function_requests(
    *, project: CompiledProject, adapter: BaseAdapter
) -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "udfPrefix": udf_prefix,
            "udfSuffix": udf_suffix,
            "tableFunctionPrefix": table_function_prefix,
            "tableFunctionSuffix": table_function_suffix,
        }
        for (
            name,
            udf_prefix,
            udf_suffix,
            table_function_prefix,
            table_function_suffix,
        ) in _function_templates(project=project, adapter=adapter)
    ]


def _function_templates(
    *, project: CompiledProject, adapter: BaseAdapter
) -> tuple[tuple[str, str, str, str, str], ...]:
    """Each function's name and the adapter's UDF and table-function call templates."""

    functions: list[tuple[str, str, str, str, str]] = []
    for function in project.functions:
        target: str | None = function.destination.qualified_name
        if target is None:
            continue
        udf_prefix, udf_suffix = _render_call_template(
            rendered=adapter.render_udf_call(
                target=target,
                call_suffix_sql=_CALL_SUFFIX_SENTINEL,
            )
        )
        table_function_prefix, table_function_suffix = _render_call_template(
            rendered=adapter.render_table_function_call(
                target=target,
                call_suffix_sql=_CALL_SUFFIX_SENTINEL,
            )
        )
        functions.append(
            (function.name, udf_prefix, udf_suffix, table_function_prefix, table_function_suffix)
        )
    return tuple(functions)


def _planning_test_requests(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...], adapter: BaseAdapter
) -> list[dict[str, object]]:
    """Build test requests whose model SQL has cursor intrinsics rendered for the test window."""

    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    windowed_indexes: tuple[int, ...] = tuple(
        index
        for index, test in enumerate(tests)
        if isinstance(test.payload, CompiledModelSqlTestPayload)
        and declares_cursor_window(test=test)
    )
    chains: tuple[tuple[str, ...], ...] = (
        resolve_sql_test_model_chains(
            project=project, tests=tuple(tests[index] for index in windowed_indexes)
        )
        if windowed_indexes
        else ()
    )
    chains_by_index: dict[int, tuple[str, ...]] = dict(zip(windowed_indexes, chains, strict=True))
    return [
        _test_request(
            test=test,
            model_query_overrides=_windowed_model_query_overrides(
                test=test,
                models_by_name=models_by_name,
                adapter=adapter,
                chain=chains_by_index.get(index),
            ),
        )
        for index, test in enumerate(tests)
    ]


def _windowed_model_query_overrides(
    *,
    test: CompiledSqlTest,
    models_by_name: dict[str, CompiledModel],
    adapter: BaseAdapter,
    chain: tuple[str, ...] | None,
) -> dict[str, str] | None:
    payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = test.payload
    if not isinstance(payload, CompiledModelSqlTestPayload):
        return None
    chain_names: frozenset[str] = frozenset(chain or ())
    overrides: dict[str, str] = {}
    for model_name, sql in payload.model_query_overrides.items():
        model: CompiledModel | None = models_by_name.get(model_name)
        overrides[model_name] = (
            sql
            if model is None
            else render_test_cursor_intrinsics(
                sql=sql,
                model=model,
                adapter=adapter,
                test=test if model_name in chain_names else None,
            )
        )
    if chain is not None:
        chain_models: tuple[CompiledModel, ...] = tuple(
            models_by_name[name] for name in chain if name in models_by_name
        )
        for model in declared_window_cursor_models(test=test, chain_models=chain_models):
            if model.name not in overrides:
                overrides[model.name] = render_test_cursor_intrinsics(
                    sql=model.query_sql, model=model, adapter=adapter, test=test
                )
    return overrides


def _test_request(
    *, test: CompiledSqlTest, model_query_overrides: dict[str, str] | None = None
) -> dict[str, object]:
    payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = test.payload
    if isinstance(payload, CompiledDirectLogicSqlTestPayload):
        payload_request: dict[str, object] = {
            "kind": "direct",
            "mode": payload.mode.value,
            "actualCte": _cte_request(cte=payload.actual_cte),
            "expectedCte": _cte_request(cte=payload.expected_cte),
            "helperCtes": [_cte_request(cte=cte) for cte in payload.helper_ctes],
        }
    else:
        payload_request = {
            "kind": "model",
            "authoredCtes": [_cte_request(cte=cte) for cte in payload.authored_ctes],
            "modelQueryOverrides": (
                payload.model_query_overrides
                if model_query_overrides is None
                else model_query_overrides
            ),
            "expectedCtes": [_cte_request(cte=cte) for cte in payload.expected_ctes],
            "expectedModelNames": list(payload.expected_model_names),
            "assertionCtes": [_cte_request(cte=cte) for cte in payload.assertion_ctes],
            "readHelperNames": list(test.read_helper_names),
            "referenceTargetModelNames": list(test.reference_target_model_names),
        }
    return {
        "name": test.name,
        "fileLabel": str(test.test_file.relative_path),
        "payload": payload_request,
    }


def _model_requests(*, project: CompiledProject, adapter: BaseAdapter) -> list[dict[str, object]]:
    return [
        {
            "name": model.name,
            "querySql": render_test_cursor_intrinsics(
                sql=model.query_sql, model=model, adapter=adapter, test=None
            ),
            "modelDependencies": _model_dependencies(model=model),
        }
        for model in project.models
    ]


def _chain_model_requests(*, project: CompiledProject) -> list[dict[str, object]]:
    """Chain ordering reads only declared dependencies, so model SQL is not sent."""

    return [
        {"name": model.name, "modelDependencies": _model_dependencies(model=model)}
        for model in project.models
    ]


def _model_dependencies(*, model: CompiledModel) -> list[str]:
    return [
        dependency.name
        for dependency in model.deps
        if dependency.resource_type == CompiledResourceType.MODEL
    ]


def _cte_request(*, cte: CompileSqlTestCte) -> dict[str, str]:
    return {"name": cte.name, "sqlBody": cte.sql_body}


def _render_call_template(*, rendered: str) -> tuple[str, str]:
    prefix, separator, suffix = rendered.partition(_CALL_SUFFIX_SENTINEL)
    if not separator or _CALL_SUFFIX_SENTINEL in suffix:
        raise NativeSqlTestPlanningError("adapter SQL function call template is not deterministic")
    return prefix, suffix


def _lexical_syntax_request(syntax: SqlLexicalSyntax) -> dict[str, object]:
    return {
        "backslashEscapeQuotes": sorted(syntax.backslash_escape_quotes),
        "escapeStringPrefix": syntax.escape_string_prefix,
        "rawStringPrefix": syntax.raw_string_prefix,
        "tripleQuotedStrings": syntax.triple_quoted_strings,
        "nestedBlockComments": syntax.nested_block_comments,
        "lineCommentPrefixes": sorted(syntax.line_comment_prefixes),
    }
