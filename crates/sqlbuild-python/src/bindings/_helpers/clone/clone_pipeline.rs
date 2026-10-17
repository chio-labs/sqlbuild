//! Compile the origin and destination environments of a clone and plan it.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::project::build_compiled_project;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::contracts::spec_resolution::resolve_target_config;
use crate::bindings::_helpers::planner_entries::clone_plans::run_clone_planning;
use crate::bindings::_helpers::records::construct::new_record_with;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;

/// The `ClonePipelineResult` fields after the two projects, in `run_clone_planning` order.
const PLANNED_FIELDS: [&str; 8] = [
    "clone_plan",
    "destination_source_entries",
    "destination_model_entries",
    "destination_seed_entries",
    "destination_function_entries",
    "origin_model_entries",
    "origin_seed_entries",
    "origin_source_entries",
];

/// The discovered project, adapter, destination connection, options and reference resolver.
pub(crate) struct ClonePipeline<'py> {
    pub(crate) discovered: Bound<'py, PyAny>,
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) connection: Bound<'py, PyAny>,
    pub(crate) options: Bound<'py, PyAny>,
    pub(crate) resolver: Bound<'py, PyAny>,
}

/// The compiled project of one target environment.
fn compiled_environment<'py>(
    pipeline: &ClonePipeline<'py>,
    target_name: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = target_name.py();
    let options: &Bound<'py, PyAny> = &pipeline.options;
    build_compiled_project(
        py,
        Some(keywords(
            py,
            &[
                ("discovered_inputs", pipeline.discovered.clone()),
                ("adapter", pipeline.adapter.clone()),
                ("selected_target", target_name.clone()),
                (
                    "resolved_connection",
                    native_field(&pipeline.connection, "config")?,
                ),
                (
                    "no_sql_validation",
                    native_field(options, "no_sql_validation")?,
                ),
                (
                    "analysis_selection",
                    new_record_with(
                        py,
                        RecordId::CompileAnalysisSelection,
                        &[("no_cache", native_field(options, "no_cache")?)],
                    )?,
                ),
                ("cli_vars", native_field(options, "cli_vars")?),
                ("external_sql_reference_resolver", pipeline.resolver.clone()),
            ],
        )?),
    )
}

/// The target whose sources a target reads: its `defer_sources_to`, or itself.
fn read_target_name<'py>(
    discovered: &Bound<'py, PyAny>,
    target_name: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = target_name.py();
    let deferred: Bound<'py, PyAny> = resolve_target_config(
        py,
        &native_field(discovered, "project_config")?,
        &native_field(discovered, "local_config")?,
        target_name,
    )?
    .getattr("defer_sources_to")?;
    if deferred.is_truthy()? {
        return Ok(deferred);
    }
    Ok(target_name.clone())
}

/// The project its sources are read from: `project` itself unless sources defer elsewhere.
fn source_project<'py>(
    pipeline: &ClonePipeline<'py>,
    project: &Bound<'py, PyAny>,
    target_name: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let read_target: Bound<'py, PyAny> = read_target_name(&pipeline.discovered, target_name)?;
    if read_target.eq(target_name)? {
        return Ok(project.clone());
    }
    compiled_environment(pipeline, &read_target)
}

/// Compile both environments, plan the clone and return the `ClonePipelineResult`.
pub(crate) fn prepared_clone_pipeline<'py>(
    pipeline: &ClonePipeline<'py>,
    (origin_target, destination_target): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = origin_target.py();
    let origin_project: Bound<'py, PyAny> = compiled_environment(pipeline, origin_target)?;
    let destination_project: Bound<'py, PyAny> =
        compiled_environment(pipeline, destination_target)?;
    let origin_source_project: Bound<'py, PyAny> =
        source_project(pipeline, &origin_project, origin_target)?;
    let destination_source_project: Bound<'py, PyAny> =
        source_project(pipeline, &destination_project, destination_target)?;
    let planned: Bound<'py, PyTuple> = run_clone_planning(
        py,
        Some(keywords(
            py,
            &[
                ("project", destination_project.clone()),
                ("select", native_field(&pipeline.options, "select")?),
                ("exclude", native_field(&pipeline.options, "exclude")?),
                ("adapter", pipeline.adapter.clone()),
                ("connection", native_field(&pipeline.connection, "handle")?),
                ("origin_project", origin_project.clone()),
                ("origin_source_project", origin_source_project),
                ("destination_source_project", destination_source_project),
            ],
        )?),
    )
    .and_then(|value| pyo3::IntoPyObjectExt::into_bound_py_any(value, py))?
    .downcast_into()?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("origin_project", origin_project),
        ("destination_project", destination_project),
    ];
    for (index, name) in PLANNED_FIELDS.iter().enumerate() {
        fields.push((*name, planned.get_item(index)?));
    }
    new_record_with(py, RecordId::ClonePipelineResult, &fields)
}

/// Run a clone pipeline with explicit compilation controls.
#[pyfunction]
#[pyo3(signature = (**request))]
pub(crate) fn run_clone_pipeline_with_options<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let request: Request<'_, 'py> = Request::new("run_clone_pipeline_with_options", request)?;
    let py: Python<'py> = request.py();
    prepared_clone_pipeline(
        &ClonePipeline {
            discovered: request.get("discovered_inputs")?,
            adapter: request.get("adapter")?,
            connection: request.get("destination_connection")?,
            options: request.get("options")?,
            resolver: request
                .optional("external_sql_reference_resolver")?
                .unwrap_or_else(|| py.None().into_bound(py)),
        },
        (
            &request.get("origin_target_name")?,
            &request.get("destination_target_name")?,
        ),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_clone_pipeline_with_options, module)?)?;
    Ok(())
}
