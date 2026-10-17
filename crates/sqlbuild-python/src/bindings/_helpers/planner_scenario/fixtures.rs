//! Materialize fixture SQL plans while preserving adapter and completion boundaries.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::planner_scenario::constants::SCENARIO_PLAN_MISSING_FIXTURE_SQL;
use crate::bindings::_helpers::planner_scenario::{
    models::SqlContext,
    sql::{required_target, resolve_sql, source_label},
    values::{error, string},
};
use crate::bindings::_helpers::records::construct::{enum_from_value, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get_or;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

pub(super) fn extract_fixtures<'py>(
    scenario: &Bound<'py, PyAny>,
    prefix: &str,
) -> PyResult<Bound<'py, PyDict>> {
    crate::bindings::_helpers::sql_test_glue::authored_ctes::prefixed_ctes(
        &native_field(scenario, "authored_ctes")?,
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
    for cte in native_field(scenario, "authored_ctes")?.try_iter()? {
        let cte = cte?;
        let name: String = native_field(&cte, "name")?.extract()?;
        if ["__source__", "__ref__", "__seed__", "__dbt_ref__"]
            .iter()
            .any(|prefix| name.starts_with(prefix))
        {
            continue;
        }
        let sql = resolve_sql(
            context,
            &native_field(&cte, "sql_body")?.extract::<String>()?,
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
        for name in native_field(graph, names)?.try_iter()? {
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
                sql = mapping_get_or(overrides, (resource, &name), sql)?;
            }
            let sql = resolve_sql(context, &sql.extract::<String>()?, true)?;
            let sql = if helpers.is_empty() {
                sql
            } else {
                format!("WITH {} {sql}", helpers.join(", "))
            };
            result.push(new_record_with(
                py,
                RecordId::ScenarioFixturePlan,
                &[
                    (
                        "kind",
                        enum_from_value(py, RecordId::ScenarioArtifactKind, kind)?,
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
