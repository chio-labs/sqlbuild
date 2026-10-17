//! Existing seed and function plan dataclass construction.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::compiled_project::loop_classes::by_attribute;
use crate::bindings::_helpers::planner_identity::metadata::build_compiled_function_fingerprint_sql;
use crate::bindings::_helpers::planner_resolution::orchestration::resolve_function_sql;
use crate::bindings::_helpers::planner_scenario::constants::SCENARIO_PLAN_UNKNOWN_SEED;
use crate::bindings::_helpers::planner_scenario::{
    models::SqlContext, sql::required_target, values::error,
};
use crate::bindings::_helpers::planner_strategy::model_entries::extract_seed_columns;
use crate::bindings::_helpers::records::construct::new_record_with;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::PyString;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

pub(super) fn seed_entries<'py>(
    project: &Bound<'py, PyAny>,
    graph: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = project.py();
    let seeds = by_attribute(&native_field(project, "seeds")?, "name")?;
    let fixtures = native_field(graph, "seed_fixture_names")?;
    let mut result: Vec<Bound<'py, PyAny>> = Vec::new();
    for name in native_field(graph, "seed_names")?.try_iter()? {
        let name = name?;
        if fixtures.contains(&name)? {
            continue;
        }
        let Some(seed) = seeds.get_item(&name)? else {
            let scenario: String = native_field(graph, "name")?.extract()?;
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
        result.push(new_record_with(
            py,
            RecordId::SeedPlanEntry,
            &[
                ("key", native_field(&seed, "key")?),
                ("name", native_field(&seed, "name")?),
                ("destination", destination),
                (
                    "file_path",
                    native_field(&native_field(&seed, "seed_file")?, "file_path")?,
                ),
                ("columns", extract_seed_columns(&seed)?.into_any()),
                (
                    "csv_settings",
                    native_field(&native_field(&seed, "schema_entry")?, "csv_settings")?,
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
    let body = resolve_function_sql(
        py,
        Some(keywords(
            py,
            &[
                ("adapter", context.adapter.clone()),
                ("function", function.clone()),
                (
                    "model_locations",
                    native_field(&context.relations, "model_locations")?,
                ),
                (
                    "seed_locations",
                    native_field(&context.relations, "seed_locations")?,
                ),
                ("function_locations", locations.clone()),
                (
                    "source_map",
                    native_field(&context.relations, "source_map")?,
                ),
                ("source_warehouse_columns", warehouse_columns.clone()),
                (
                    "star_exclude_keyword",
                    context.adapter.call_method0("star_exclude_keyword")?,
                ),
            ],
        )?),
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
        fields.push((name, native_field(function, name)?));
    }
    fields.push(("body_sql", body));
    fields.push((
        "fingerprint_query_sql",
        PyString::new(py, &build_compiled_function_fingerprint_sql(function)?).into_any(),
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
        fields.push((name, native_field(function, name)?));
    }
    new_record_with(py, RecordId::FunctionPlanEntry, &fields)
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
