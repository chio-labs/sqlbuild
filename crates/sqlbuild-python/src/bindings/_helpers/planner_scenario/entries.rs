//! Existing seed and function plan dataclass construction.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::compiled_project::loop_classes::by_attribute;
use crate::bindings::_helpers::planner_scenario::constants::SCENARIO_PLAN_UNKNOWN_SEED;
use crate::bindings::_helpers::planner_scenario::{
    models::SqlContext,
    sql::required_target,
    values::{MODELS, error},
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

pub(super) fn seed_entries<'py>(
    project: &Bound<'py, PyAny>,
    graph: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = project.py();
    let seeds = by_attribute(&project.getattr("seeds")?, "name")?;
    let fixtures = graph.getattr("seed_fixture_names")?;
    let mut result: Vec<Bound<'py, PyAny>> = Vec::new();
    for name in graph.getattr("seed_names")?.try_iter()? {
        let name = name?;
        if fixtures.contains(&name)? {
            continue;
        }
        let Some(seed) = seeds.get_item(&name)? else {
            let scenario: String = graph.getattr("name")?.extract()?;
            let name: String = name.extract()?;
            return Err(error(
                py,
                &format!("Scenario '{scenario}' requires unknown seed '{name}'"),
                SCENARIO_PLAN_UNKNOWN_SEED,
                None,
            )?);
        };
        let destination = required_target(
            relations,
            "seed_locations",
            &name.extract::<String>()?,
            "seed",
        )?;
        result.push(call_with(
            &imported(py, MODELS, "SeedPlanEntry")?,
            &[
                ("key", seed.getattr("key")?),
                ("name", seed.getattr("name")?),
                ("destination", destination),
                (
                    "file_path",
                    seed.getattr("seed_file")?.getattr("file_path")?,
                ),
                (
                    "columns",
                    imported(py, "sqlbuild._native", "extract_seed_columns")?.call1((&seed,))?,
                ),
                (
                    "csv_settings",
                    seed.getattr("schema_entry")?.getattr("csv_settings")?,
                ),
            ],
        )?);
    }
    PyTuple::new(py, result)
}

pub(super) fn function_entry<'py>(
    function: &Bound<'py, PyAny>,
    context: &SqlContext<'py>,
    locations: &Bound<'py, PyAny>,
    warehouse_columns: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = function.py();
    let body = call_with(
        &imported(py, "sqlbuild._native", "resolve_function_sql")?,
        &[
            ("adapter", context.adapter.clone()),
            ("function", function.clone()),
            (
                "model_locations",
                context.relations.getattr("model_locations")?,
            ),
            (
                "seed_locations",
                context.relations.getattr("seed_locations")?,
            ),
            ("function_locations", locations.clone()),
            ("source_map", context.relations.getattr("source_map")?),
            ("source_warehouse_columns", warehouse_columns.clone()),
            (
                "star_exclude_keyword",
                context.adapter.call_method0("star_exclude_keyword")?,
            ),
        ],
    )?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = Vec::new();
    for name in [
        "key",
        "name",
        "relative_path",
        "destination",
        "arguments",
        "returns",
    ] {
        fields.push((name, function.getattr(name)?));
    }
    fields.push(("body_sql", body));
    fields.push((
        "fingerprint_query_sql",
        imported(
            py,
            "sqlbuild._native",
            "build_compiled_function_fingerprint_sql",
        )?
        .call1((function,))?,
    ));
    for name in [
        "fingerprint_destination",
        "return_columns",
        "language",
        "source_file_path",
        "runtime_version",
        "entry_point",
        "packages",
    ] {
        fields.push((name, function.getattr(name)?));
    }
    call_with(&imported(py, MODELS, "FunctionPlanEntry")?, &fields)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn build_scenario_seed_entries<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let args = KeywordArguments::read(
        py,
        "build_scenario_seed_entries",
        kwargs,
        (&["project", "graph_plan", "relation_plan"], &[]),
    )?;
    seed_entries(
        &args.value("project")?,
        &args.value("graph_plan")?,
        &args.value("relation_plan")?,
    )
}
