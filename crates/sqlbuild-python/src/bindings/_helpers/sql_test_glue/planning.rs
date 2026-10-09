//! Plan compiled SQL tests from the compiled project's own objects, without a JSON request.

use std::collections::{BTreeMap, HashMap};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::compiler::main::sql_test_chains::resolve_sql_test_chains;
use sqlbuild_analysis::compiler::main::sql_test_glue::plan_sql_test_batch;
use sqlbuild_analysis::compiler::main::sql_test_plan_errors::sql_test_plan_error_messages;
use sqlbuild_analysis::compiler::models::{
    SqlTestAssertionStep, SqlTestChainBatch, SqlTestChainModel, SqlTestChainStep, SqlTestCte,
    SqlTestPlan, SqlTestPlanBatch, SqlTestPlanFunction, SqlTestPlanModel, SqlTestPlanPayload,
    SqlTestPlanTest,
};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use crate::bindings::types::CompilerDetach;

const MODEL_RESOURCE_TYPE: &str = "model";
const PLANNING_WORKERS: usize = 4;

type CtePair = (String, String);
/// `(model, SQL, expected SQL, lifted CTEs, body, expected columns, expected lifted CTEs)`.
type ChainRow = (
    String,
    String,
    Option<String>,
    Vec<CtePair>,
    Option<String>,
    Option<Vec<String>>,
    Vec<CtePair>,
);
/// `(name, resolved SQL, lifted CTEs, comparison body)`.
type AssertionRow = (String, String, Vec<CtePair>, Option<String>);
/// `(model, severity, message)`.
type WarningRow = (Option<String>, &'static str, String);
/// `(SQL, chain, assertions, model names, warnings, distinct error messages)`.
type PlanRow = (
    Option<String>,
    Vec<ChainRow>,
    Vec<AssertionRow>,
    Vec<String>,
    Vec<WarningRow>,
    Vec<String>,
);

/// The Python planning request: compiled models and tests, with the adapter's facts.
#[derive(FromPyObject)]
struct PlanningRequest<'py> {
    #[pyo3(attribute)]
    models: Vec<Bound<'py, PyAny>>,
    /// Cursor-rendered SQL by model index, for models whose SQL uses cursor intrinsics.
    #[pyo3(attribute)]
    rendered_model_sql: HashMap<usize, String>,
    #[pyo3(attribute)]
    functions: Vec<(String, String, String, String, String)>,
    #[pyo3(attribute)]
    tests: Vec<Bound<'py, PyAny>>,
    /// Cursor-rendered model query overrides by test index, replacing the test's own.
    #[pyo3(attribute)]
    rendered_test_overrides: HashMap<usize, BTreeMap<String, String>>,
    #[pyo3(attribute)]
    sql_analysis_enabled: bool,
    #[pyo3(attribute)]
    sql_analysis_dialect: Option<String>,
    #[pyo3(attribute)]
    set_difference_operator: String,
    #[pyo3(attribute)]
    requires_derived_table_aliases: bool,
    #[pyo3(attribute)]
    lexical_syntax: LexicalSyntaxInput,
    #[pyo3(attribute)]
    render_sql: bool,
    #[pyo3(attribute)]
    include_plan: bool,
}

/// The Python chain request: compiled models and the tests whose chains to resolve.
#[derive(FromPyObject)]
struct ChainRequest<'py> {
    #[pyo3(attribute)]
    models: Vec<Bound<'py, PyAny>>,
    #[pyo3(attribute)]
    tests: Vec<Bound<'py, PyAny>>,
    #[pyo3(attribute)]
    lexical_syntax: LexicalSyntaxInput,
}

/// Each test's ordered unmocked model chain; direct-logic tests have none.
#[pyfunction]
fn resolve_compiled_sql_test_chains(
    py: Python<'_>,
    request: ChainRequest<'_>,
) -> PyResult<Vec<Vec<String>>> {
    let batch = SqlTestChainBatch {
        models: request
            .models
            .iter()
            .map(|model| {
                Ok(SqlTestChainModel {
                    name: model.getattr("name")?.extract()?,
                    model_dependencies: model_dependencies(model)?,
                })
            })
            .collect::<PyResult<_>>()?,
        tests: request
            .tests
            .iter()
            .map(|test| plan_test(test, None))
            .collect::<PyResult<_>>()?,
        lexical_syntax: request.lexical_syntax.into(),
    };
    py.compiler_detach(|| resolve_sql_test_chains(batch))
        .map_err(value_error)
}

/// Plan SQL tests in one batch and return each plan with its distinct error messages.
#[pyfunction]
fn plan_compiled_sql_tests(
    py: Python<'_>,
    request: PlanningRequest<'_>,
) -> PyResult<(Vec<PlanRow>, u64, u64)> {
    let batch: SqlTestPlanBatch = planning_batch(request)?;
    let outcome = py
        .compiler_detach(|| plan_sql_test_batch(batch))
        .map_err(value_error)?;
    Ok((
        outcome.plans.into_iter().map(plan_row).collect(),
        outcome.planning_ns,
        outcome.rendering_ns,
    ))
}

fn planning_batch(mut request: PlanningRequest<'_>) -> PyResult<SqlTestPlanBatch> {
    let models: Vec<SqlTestPlanModel> = request
        .models
        .iter()
        .enumerate()
        .map(|(index, model)| plan_model(model, request.rendered_model_sql.remove(&index)))
        .collect::<PyResult<_>>()?;
    let tests: Vec<SqlTestPlanTest> = request
        .tests
        .iter()
        .enumerate()
        .map(|(index, test)| plan_test(test, request.rendered_test_overrides.remove(&index)))
        .collect::<PyResult<_>>()?;
    Ok(SqlTestPlanBatch {
        models,
        functions: request.functions.into_iter().map(plan_function).collect(),
        tests,
        sql_analysis_enabled: request.sql_analysis_enabled,
        sql_analysis_dialect: request.sql_analysis_dialect,
        set_difference_operator: request.set_difference_operator,
        requires_derived_table_aliases: request.requires_derived_table_aliases,
        workers: PLANNING_WORKERS,
        render_sql: request.render_sql,
        include_plan: request.include_plan,
        lexical_syntax: request.lexical_syntax.into(),
    })
}

fn plan_model(
    model: &Bound<'_, PyAny>,
    rendered_sql: Option<String>,
) -> PyResult<SqlTestPlanModel> {
    Ok(SqlTestPlanModel {
        name: model.getattr("name")?.extract()?,
        query_sql: match rendered_sql {
            Some(sql) => sql,
            None => model.getattr("query_sql")?.extract()?,
        },
        model_dependencies: model_dependencies(model)?,
    })
}

/// The names of the models among a compiled model's dependencies, in dependency order.
fn model_dependencies(model: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    for dependency in model.getattr("deps")?.try_iter()? {
        let dependency = dependency?;
        if dependency
            .getattr("resource_type")?
            .eq(MODEL_RESOURCE_TYPE)?
        {
            names.push(dependency.getattr("name")?.extract()?);
        }
    }
    Ok(names)
}

fn plan_function(
    (name, udf_prefix, udf_suffix, table_function_prefix, table_function_suffix): (
        String,
        String,
        String,
        String,
        String,
    ),
) -> SqlTestPlanFunction {
    SqlTestPlanFunction {
        name,
        udf_prefix: Some(udf_prefix),
        udf_suffix: Some(udf_suffix),
        table_function_prefix: Some(table_function_prefix),
        table_function_suffix: Some(table_function_suffix),
    }
}

fn plan_test(
    test: &Bound<'_, PyAny>,
    rendered_overrides: Option<BTreeMap<String, String>>,
) -> PyResult<SqlTestPlanTest> {
    let payload = test.getattr("payload")?;
    let payload: SqlTestPlanPayload = if payload.hasattr("actual_cte")? {
        SqlTestPlanPayload::Direct {
            mode: payload.getattr("mode")?.extract()?,
            actual_cte: cte(&payload.getattr("actual_cte")?)?,
            expected_cte: cte(&payload.getattr("expected_cte")?)?,
            helper_ctes: ctes(&payload, "helper_ctes")?,
        }
    } else {
        SqlTestPlanPayload::Model {
            authored_ctes: ctes(&payload, "authored_ctes")?,
            model_query_overrides: match rendered_overrides {
                Some(overrides) => overrides,
                None => payload.getattr("model_query_overrides")?.extract()?,
            },
            expected_ctes: ctes(&payload, "expected_ctes")?,
            expected_model_names: payload.getattr("expected_model_names")?.extract()?,
            assertion_ctes: ctes(&payload, "assertion_ctes")?,
            read_helper_names: Some(test.getattr("read_helper_names")?.extract()?),
            reference_target_model_names: Some(
                test.getattr("reference_target_model_names")?.extract()?,
            ),
        }
    };
    Ok(SqlTestPlanTest {
        name: test.getattr("name")?.extract()?,
        file_label: test
            .getattr("test_file")?
            .getattr("relative_path")?
            .str()?
            .extract()?,
        payload,
    })
}

fn ctes(owner: &Bound<'_, PyAny>, attribute: &str) -> PyResult<Vec<SqlTestCte>> {
    owner
        .getattr(attribute)?
        .try_iter()?
        .map(|value| cte(&value?))
        .collect()
}

fn cte(value: &Bound<'_, PyAny>) -> PyResult<SqlTestCte> {
    Ok(SqlTestCte {
        name: value.getattr("name")?.extract()?,
        sql_body: value.getattr("sql_body")?.extract()?,
    })
}

fn plan_row(plan: SqlTestPlan) -> PlanRow {
    let error_messages: Vec<String> = sql_test_plan_error_messages(&plan);
    (
        plan.sql,
        plan.chain.into_iter().map(chain_row).collect(),
        plan.assertions.into_iter().map(assertion_row).collect(),
        plan.model_names,
        plan.warnings
            .into_iter()
            .map(|warning| (warning.model_name, warning.severity, warning.message))
            .collect(),
        error_messages,
    )
}

fn chain_row(step: SqlTestChainStep) -> ChainRow {
    (
        step.model_name,
        step.resolved_sql,
        step.expected_cte_sql,
        step.lifted_ctes,
        step.comparison_body_sql,
        step.expected_columns,
        step.expected_lifted_ctes,
    )
}

fn assertion_row(step: SqlTestAssertionStep) -> AssertionRow {
    (
        step.name,
        step.resolved_sql,
        step.lifted_ctes,
        step.comparison_body_sql,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_compiled_sql_tests, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_compiled_sql_test_chains, module)?)?;
    Ok(())
}
