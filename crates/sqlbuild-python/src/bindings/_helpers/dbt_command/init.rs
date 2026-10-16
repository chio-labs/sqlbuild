//! `sqb dbt init`: create or preview a SQLBuild twin project for a dbt project.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::dbt_command::constants::DBT_PROJECT_FILE;
use sqlbuild_core::dbt_command::main::render_dbt_init_preview::render_dbt_init_preview;
use sqlbuild_core::dbt_command::main::render_dbt_init_summary::render_dbt_init_summary;
use sqlbuild_core::dbt_command::models::DbtInitSummary;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::dbt_command::support::{color_enabled, flag, path, stream};
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

fn missing_project(py: Python<'_>) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", "C242")?;
        registry::error(py, ErrorId::CliUser)?.call(
            ("sqb dbt init requires --project-dir pointing at a dbt project",),
            Some(&options),
        )
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// `Path(value)`, or `None` when the option was not given.
fn optional_path<'py>(value: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if value.is_none() {
        return Ok(value);
    }
    imported(value.py(), "pathlib", "Path")?.call1((value,))
}

/// The dbt project directory: the option, else `.` when the working directory is a dbt project.
fn dbt_project_dir<'py>(request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let given: Bound<'py, PyAny> = request.getattr("dbt_project_dir")?;
    if !given.is_none() {
        return optional_path(given);
    }
    let in_project: bool = request
        .getattr("cwd")?
        .call_method1("__truediv__", (DBT_PROJECT_FILE,))?
        .call_method0("exists")?
        .is_truthy()?;
    if in_project {
        return path(py, ".");
    }
    Err(missing_project(py))
}

fn text(result: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    Ok(result.getattr(name)?.str()?.to_string())
}

fn summary(result: &Bound<'_, PyAny>) -> PyResult<DbtInitSummary> {
    Ok(DbtInitSummary {
        output_dir: text(result, "output_dir")?,
        project_file: text(result, "project_file")?,
        project_name: text(result, "project_name")?,
        adapter: text(result, "adapter")?,
        target_name: text(result, "target_name")?,
        profile_name: text(result, "profile_name")?,
        toml: text(result, "toml")?,
    })
}

/// Execute SQLBuild-owned `sqb dbt init`.
#[pyfunction]
#[pyo3(signature = (request))]
fn run_dbt_init_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let project_dir: Bound<'_, PyAny> = dbt_project_dir(request)?;
    let use_color: bool = color_enabled(py)?;
    let progress: Bound<'_, PyAny> = call_with(
        &registry::native(py, NativeAttr::DbtInitProgressReporter)?,
        &[
            ("stream", stream(py, "stdout")?),
            ("use_color", flag(py, use_color)),
        ],
    )?;
    let callbacks: Bound<'_, PyAny> = call_with(
        &registry::class(py, RecordId::DbtInitProgressCallbacks)?,
        &[
            ("start", progress.getattr("start")?),
            ("complete", progress.getattr("complete")?),
        ],
    )?;
    let init_request: Bound<'_, PyAny> = call_with(
        &registry::class(py, RecordId::DbtInitRequest)?,
        &[
            ("cwd", request.getattr("cwd")?),
            ("dbt_project_dir", project_dir),
            (
                "profiles_dir",
                optional_path(request.getattr("profiles_dir")?)?,
            ),
            ("profile_name", request.getattr("profile_name")?),
            ("target_name", request.getattr("target_name")?),
            (
                "sqb_output_dir",
                optional_path(request.getattr("sqb_output_dir")?)?,
            ),
            ("dry_run", request.getattr("dry_run")?),
            ("overwrite", request.getattr("overwrite")?),
            ("skip_dbt_debug", request.getattr("skip_dbt_debug")?),
            ("progress_callbacks", callbacks),
        ],
    )?;
    call_with(
        &registry::native(py, NativeAttr::ValidateDbtInitProject)?,
        &[("request", init_request.clone())],
    )?;
    let result: Bound<'_, PyAny> = call_with(
        &registry::native(py, NativeAttr::BuildDbtInitProject)?,
        &[("request", init_request)],
    )?;
    let style: CliStyle = CliStyle { use_color };
    let stdout: Bound<'_, PyAny> = stream(py, "stdout")?;
    if request.getattr("dry_run")?.is_truthy()? {
        stdout.call_method1(
            "write",
            (render_dbt_init_preview(&summary(&result)?, style),),
        )?;
        return Ok(0);
    }
    stdout.call_method1(
        "write",
        (render_dbt_init_summary(&summary(&result)?, style),),
    )?;
    for warning in result.getattr("warnings")?.try_iter()? {
        stream(py, "stderr")?
            .call_method1("write", (format!("Warning: {}\n", warning?.str()?),))?;
    }
    Ok(0)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_dbt_init_command, module)?)?;
    Ok(())
}
