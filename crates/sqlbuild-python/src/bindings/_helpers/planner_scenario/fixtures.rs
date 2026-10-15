//! Materialize fixture SQL plans while preserving adapter and completion boundaries.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_scenario::constants::SCENARIO_PLAN_MISSING_FIXTURE_SQL;
use crate::bindings::_helpers::planner_scenario::{
    models::SqlContext,
    sql::{required_target, resolve_sql, source_label},
    values::{MODELS, TYPES, error, string},
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

pub(super) fn extract_fixtures<'py>(
    scenario: &Bound<'py, PyAny>,
    prefix: &str,
) -> PyResult<Bound<'py, PyDict>> {
    crate::bindings::_helpers::sql_test_glue::authored_ctes::prefixed_ctes(
        &scenario.getattr("authored_ctes")?,
        prefix,
    )
}

pub(super) fn fixture_plans<'py>(
    scenario: &Bound<'py, PyAny>,
    graph: &Bound<'py, PyAny>,
    context: &SqlContext<'py>,
    overrides: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = scenario.py();
    let mut helpers: Vec<String> = Vec::new();
    for cte in scenario.getattr("authored_ctes")?.try_iter()? {
        let cte = cte?;
        let name: String = cte.getattr("name")?.extract()?;
        if ["__source__", "__ref__", "__seed__", "__dbt_ref__"]
            .iter()
            .any(|prefix| name.starts_with(prefix))
        {
            continue;
        }
        let sql = resolve_sql(
            context,
            &cte.getattr("sql_body")?.extract::<String>()?,
            true,
        )?;
        helpers.push(format!("{name} AS ({sql})"));
    }
    let mut result: Vec<Bound<'py, PyAny>> = Vec::new();
    for (kind, resource, names, locations) in [
        (
            "source",
            "source",
            "source_fixture_names",
            "source_fixture_locations",
        ),
        ("ref", "model", "ref_fixture_names", "ref_fixture_locations"),
        (
            "seed",
            "seed",
            "seed_fixture_names",
            "seed_fixture_locations",
        ),
        (
            "dbt_ref",
            "dbt_ref",
            "dbt_ref_fixture_names",
            "dbt_ref_fixture_locations",
        ),
    ] {
        let fixtures = extract_fixtures(scenario, &format!("__{kind}__"))?;
        for name in graph.getattr(names)?.try_iter()? {
            let name: String = name?.extract()?;
            let target = required_target(&context.relations, locations, &name, kind)?;
            let Some(mut sql) = fixtures.get_item(&name)? else {
                return Err(error(
                    py,
                    &format!("Scenario is missing {kind} fixture SQL '{name}'"),
                    SCENARIO_PLAN_MISSING_FIXTURE_SQL,
                    None,
                )?);
            };
            if kind != super::constants::DBT_REF && !overrides.is_none() {
                sql = overrides.call_method1("get", ((resource, &name), sql))?;
            }
            let sql = resolve_sql(context, &sql.extract::<String>()?, true)?;
            let sql = if helpers.is_empty() {
                sql
            } else {
                format!("WITH {} {sql}", helpers.join(", "))
            };
            result.push(call_with(
                &imported(py, MODELS, "ScenarioFixturePlan")?,
                &[
                    (
                        "kind",
                        imported(py, TYPES, "ScenarioArtifactKind")?.call1((kind,))?,
                    ),
                    ("logical_name", string(py, &name)),
                    ("destination", target),
                    ("sql", string(py, &sql)),
                ],
            )?);
        }
    }
    PyTuple::new(py, result)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn build_scenario_fixture_plans<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let args = KeywordArguments::read(
        py,
        "build_scenario_fixture_plans",
        kwargs,
        (
            &[
                "scenario",
                "graph_plan",
                "relation_plan",
                "adapter",
                "source_lexical_syntax",
            ],
            &["fixture_sql_overrides"],
        ),
    )?;
    let scenario = args.value("scenario")?;
    let context = SqlContext {
        adapter: args.value("adapter")?,
        relations: args.value("relation_plan")?,
        syntax: args.value("source_lexical_syntax")?,
        label: source_label(&scenario)?,
    };
    fixture_plans(
        &scenario,
        &args.value("graph_plan")?,
        &context,
        &args.value("fixture_sql_overrides")?,
    )
}
