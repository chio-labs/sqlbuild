//! Host column migration planning while Python owns warehouse inspection.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_migrations::column_objects::{model, replace};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

/// Decide column renames and return the existing planning result model.
#[pyfunction]
#[pyo3(signature = (**options))]
fn plan_column_migrations<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "plan_column_migrations",
        options,
        (
            &[
                "runtime",
                "scope",
                "snapshot",
                "full_refresh_model_names",
                "physical_relations",
                "overrides",
                "deferral",
                "source_columns",
            ],
            &[],
        ),
    )?;
    let runtime = args.value("runtime")?;
    let snapshot = args.value("snapshot")?;
    let adapter = runtime.getattr("adapter")?;
    let candidates = super::column_candidates::candidates(
        &args,
        &adapter.call_method0("sql_analysis_dialect")?,
    )?;
    if candidates.is_empty() {
        return model(py, "ColumnMigrationPlanning", &[("snapshot", snapshot)]);
    }
    let database = call_with(
        &imported(py, "sqlbuild._native", "migration_planning_database")?,
        &[("runtime", runtime.clone())],
    )?;
    let state = call_with(
        &imported(
            py,
            "sqlbuild.compiler.planner.classes.migration_state_inspection",
            "MigrationStateInspection",
        )?,
        &[
            ("adapter", adapter),
            ("connection", runtime.getattr("connection")?),
            ("database", database),
        ],
    )?;
    let schemas = PySet::empty(py)?;
    for candidate in &candidates {
        let schema = candidate.model.getattr("destination")?.getattr("schema")?;
        if !schema.is_none() {
            schemas.add(schema)?;
        }
    }
    call_with(
        &state.getattr("inspect_column_events")?,
        &[("schemas", schemas.into_any())],
    )?;
    let inputs = call_with(
        &imported(
            py,
            "sqlbuild.compiler.planner.classes.known_input_columns",
            "KnownInputColumns",
        )?,
        &[
            ("model_columns", snapshot.getattr("existing_columns")?),
            ("source_columns", args.value("source_columns")?),
        ],
    )?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut hints: Vec<Bound<'py, PyAny>> = Vec::new();
    for candidate in &candidates {
        let decided = super::column_entries::decide(
            &runtime,
            candidate,
            &state.getattr("column_events")?,
            &inputs,
        )?;
        let physical = args
            .value("physical_relations")?
            .call_method1("get", (candidate.model.getattr("name")?,))?;
        let checked = super::column_entries::checked(&runtime, candidate, decided, &physical)?;
        for hint in super::column_entries::hints(candidate, &checked.entries)?.try_iter()? {
            hints.push(hint?);
        }
        entries.extend(checked.entries);
        warnings.extend(checked.warnings);
    }
    let policy = call_with(
        &imported(py, "sqlbuild._native", "migration_missing_origin_policy")?,
        &[("runtime", runtime)],
    )?;
    for entry in &mut entries {
        *entry = replace(entry, &[("missing_origin_policy", policy.clone())])?;
        if let Some(warning) = super::column_warnings::entry_warning(entry)? {
            warnings.push(warning);
        }
    }
    let overlaid = super::column_overlay::overlay(&snapshot, &candidates, &entries, &inputs)?;
    let snapshot = super::column_overlay::cursors(&args, overlaid, &entries)?;
    model(
        py,
        "ColumnMigrationPlanning",
        &[
            ("snapshot", snapshot),
            ("entries", PyTuple::new(py, entries)?.into_any()),
            ("hints", PyTuple::new(py, hints)?.into_any()),
            ("warnings", PyTuple::new(py, warnings)?.into_any()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_column_migrations, module)?)
}
