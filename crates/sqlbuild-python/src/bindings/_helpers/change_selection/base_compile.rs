//! The base-revision side of `--since`: compile an exported tree and write its snapshot.

use std::path::PathBuf;

use pyo3::prelude::{
    Bound, IntoPyObject, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::definition_changes::main::definition_snapshot_json::definition_snapshot_json;
use sqlbuild_analysis::definition_changes::models::DefinitionSnapshot;

use crate::bindings::_helpers::boundary::python_calls::{KeywordArguments, keywords};
use crate::bindings::_helpers::change_selection::definition_snapshot::definition_snapshot;
use crate::bindings::_helpers::command_runtime::invocation::resolve_adapter_connection_context;
use crate::bindings::_helpers::compile_driver::discovery::discover_project_inputs;
use crate::bindings::_helpers::compile_driver::pipeline_entries::run_compile_only_pipeline;
use crate::bindings::_helpers::dbt_interop::reference_resolver::resolve_external_sql_reference_resolver;
use crate::bindings::_helpers::records::construct::new_record_with;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;

fn flag(py: Python<'_>, value: bool) -> Bound<'_, PyAny> {
    PyBool::new(py, value).to_owned().into_any()
}

/// Compile an exported base tree without SQL analysis and write its definition snapshot.
#[pyfunction]
#[pyo3(signature = (**options))]
fn write_base_definition_snapshot(
    py: Python<'_>,
    options: Option<Bound<'_, PyDict>>,
) -> PyResult<()> {
    let arguments: KeywordArguments<'_> = KeywordArguments::read(
        py,
        "write_base_definition_snapshot",
        options,
        (
            &["project_dir", "output_path"],
            &["selected_target", "cli_vars"],
        ),
    )?;
    let none = || py.None().into_bound(py);
    let project_dir: PathBuf = arguments.value("project_dir")?.extract()?;
    let output_path: PathBuf = arguments.value("output_path")?.extract()?;
    let directory: Bound<'_, PyAny> = project_dir.clone().into_pyobject(py)?.into_any();
    let target: Bound<'_, PyAny> = arguments.value("selected_target")?;
    let vars: Bound<'_, PyAny> = arguments.value("cli_vars")?;
    let discovered: Bound<'_, PyAny> = discover_project_inputs(
        py,
        Some(keywords(py, &[("project_dir", directory.clone())])?),
    )?;
    let context: Bound<'_, PyAny> = resolve_adapter_connection_context(
        &discovered,
        &directory,
        (target.clone(), vars.clone()),
        false,
    )?;
    let resolver: Bound<'_, PyAny> =
        resolve_external_sql_reference_resolver(directory.clone(), discovered.clone())?;
    let options: Bound<'_, PyAny> = new_record_with(
        py,
        RecordId::CompilePipelineOptions,
        &[
            ("selected_target", target),
            ("no_sql_validation", flag(py, true)),
            ("source_deferral_enabled", flag(py, false)),
            (
                "connection_config",
                native_field(&context, "connection_config")?,
            ),
            ("cli_vars", vars),
            ("external_sql_reference_resolver", resolver),
        ],
    )?;
    let pipeline: Bound<'_, PyAny> = run_compile_only_pipeline(
        py,
        Some(keywords(
            py,
            &[
                ("discovered_inputs", discovered),
                ("adapter", native_field(&context, "adapter")?),
                ("options", options),
                ("on_progress", none()),
            ],
        )?),
    )?;
    let snapshot: DefinitionSnapshot =
        definition_snapshot(&native_field(&pipeline, "project")?, &project_dir)?;
    std::fs::write(&output_path, definition_snapshot_json(&snapshot))?;
    Ok(())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(write_base_definition_snapshot, module)?)
}
