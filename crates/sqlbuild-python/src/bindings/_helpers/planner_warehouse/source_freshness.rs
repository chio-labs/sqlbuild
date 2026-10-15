//! Direct planner source freshness observation and the warnings for unknown freshness.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};
use crate::bindings::_helpers::planner_phases::objects::{
    model_key_names, planner_model, replace, text, tuple,
};
use crate::bindings::_helpers::planner_warehouse::constants::{
    FRESHNESS_PLANNING, FRESHNESS_PROPAGATION, RUN_SCOPE,
};
use crate::bindings::_helpers::planner_warehouse::snapshot::{destination_nodes, lower};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::PyDict as KeywordDict;
use pyo3::types::{PyBool, PyDict, PyDictMethods};
use sqlbuild_analysis::planner_warehouse::main::freshness_unknown_message::freshness_unknown_message;
use std::collections::BTreeSet;

/// One warning per reason that left configured source freshness unknown.
#[pyfunction]
#[pyo3(name = "build_source_freshness_unknown_warnings")]
#[pyo3(signature = (*, source_freshness))]
pub(crate) fn source_freshness_unknown_warnings<'py>(
    source_freshness: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = source_freshness.py();
    let mut reasons: Vec<(String, Vec<String>)> = Vec::new();
    for unknown in source_freshness
        .getattr("unknown_sources")?
        .call_method0("values")?
        .try_iter()?
    {
        let unknown = unknown?;
        let reason: String = unknown.getattr("reason")?.str()?.extract()?;
        if freshness_unknown_message(&reason, &[]).is_none() {
            continue;
        }
        let name: String = unknown.getattr("source_name")?.extract()?;
        match reasons.iter_mut().find(|(existing, _)| *existing == reason) {
            Some((_, names)) => names.push(name),
            None => reasons.push((reason, vec![name])),
        }
    }
    let mut warnings: Vec<_> = Vec::new();
    for (reason, names) in reasons {
        if let Some(message) = freshness_unknown_message(&reason, &names) {
            warnings.push(planner_model(
                py,
                "PlanWarning",
                &[
                    ("model_name", py.None().into_bound(py)),
                    (
                        "severity",
                        imported(py, "sqlbuild.compiler.planner.types", "WarningSeverity")?
                            .getattr("WARNING")?,
                    ),
                    ("message", text(py, &message)),
                ],
            )?);
        }
    }
    tuple(py, warnings)
}

fn state_database<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    for node in destination_nodes(project)? {
        let database = node.getattr("destination")?.getattr("database")?;
        if !database.is_none() {
            return Ok(database);
        }
    }
    Ok(project.py().None().into_bound(project.py()))
}

fn state_schemas(
    project: &Bound<'_, PyAny>,
    scope: &Bound<'_, PyAny>,
) -> PyResult<BTreeSet<String>> {
    let mut schemas: BTreeSet<_> = BTreeSet::new();
    for node in destination_nodes(project)? {
        let schema = node.getattr("destination")?.getattr("schema")?;
        if !schema.is_none() {
            schemas.insert(schema.extract()?);
        }
    }
    if schemas.is_empty() {
        let models = scope.getattr("models_by_name")?;
        for name in model_key_names(&scope.getattr("selected_keys")?)? {
            let model = models.call_method1("get", (name,))?;
            if model.is_none() {
                continue;
            }
            let schema = model.getattr("destination")?.getattr("schema")?;
            if !schema.is_none() {
                schemas.insert(schema.extract()?);
            }
        }
    }
    Ok(schemas)
}

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_planner_source_freshness_result<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_planner_source_freshness_result",
        options,
        (
            &["project", "adapter", "connection", "scope", "relations"],
            &["freshness_state_schemas"],
        ),
    )?;
    let project = &args.value("project")?;
    let adapter = &args.value("adapter")?;
    let connection = &args.value("connection")?;
    let scope = &args.value("scope")?;
    let relations = &args.value("relations")?;
    let freshness_state_schemas = &args.value("freshness_state_schemas")?;

    let py = project.py();
    let schemas = state_schemas(project, scope)?;
    let mut lowered_state: BTreeSet<String> = BTreeSet::new();
    if !freshness_state_schemas.is_none() {
        let existing = freshness_state_schemas;
        for schema in existing.try_iter()? {
            lowered_state.insert(schema?.extract()?);
        }
    }
    let exists = PyDict::new(py);
    for schema in &schemas {
        exists.set_item(
            schema,
            PyBool::new(py, lowered_state.contains(&lower(&text(py, schema))?)),
        )?;
    }
    let sources = tuple(
        py,
        relations
            .getattr("source_read_map")?
            .call_method0("values")?
            .try_iter()?
            .collect::<PyResult<_>>()?,
    )?;
    let observed_at = imported(py, "datetime", "datetime")?
        .call_method1("now", (imported(py, "datetime", "UTC")?,))?;
    let result = within(
        &imported(py, RUN_SCOPE.0, RUN_SCOPE.1)?.call1((project.getattr("run_id")?,))?,
        |_| {
            call_with(
                &imported(py, FRESHNESS_PLANNING.0, FRESHNESS_PLANNING.1)?,
                &[
                    ("adapter", adapter.clone()),
                    ("connection", connection.clone()),
                    ("sources", sources),
                    ("state_database", state_database(project)?),
                    (
                        "state_schemas",
                        tuple(py, schemas.iter().map(|schema| text(py, schema)).collect())?,
                    ),
                    ("observed_at", observed_at),
                    ("run_id", text(py, "planning")),
                    (
                        "render_qualified_name",
                        adapter.getattr("render_qualified_name")?,
                    ),
                    ("state_table_exists_by_schema", exists.into_any()),
                    (
                        "filter_previous_to_sources",
                        PyBool::new(py, true).to_owned().into_any(),
                    ),
                ],
            )
        },
    )?;
    let propagation = call_with(
        &imported(py, FRESHNESS_PROPAGATION.0, FRESHNESS_PROPAGATION.1)?,
        &[
            ("source_freshness", result.clone()),
            ("scope", scope.clone()),
        ],
    )?;
    replace(&result, &[("propagation", propagation)])
}
