//! Stage captures: frontier objects written as canonical JSON so compiles compare stage by stage.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_cache::stage_capture::constants::OMITTED_ATTRIBUTES;
use sqlbuild_cache::stage_capture::main::mask_capture_noise::mask_capture_noise as masked;

use crate::bindings::_helpers::compile_driver::python_calls::{
    call_with, imported, keywords, within,
};
use crate::bindings::_helpers::frontier::encoder::{CaptureEncoder, emit_error};

const CAPTURE_DIR_ENV_VAR: &str = "SQLBUILD_COMPILER_STAGE_CAPTURE_DIR";
const CAPTURE_SUFFIX: &str = ".json";
const PLAN_CAPTURE_DIR_ENV_VAR: &str = "SQLBUILD_PLANNER_CAPTURE_DIR";
const PLAN_CAPTURE_NAME: &str = "plan_output";
const FRONTIER_CONSTANTS_MODULE: &str = "sqlbuild.compiler.frontier.constants";

/// The capture document of `value`, or the shared nodes written before encoding failed.
fn capture_text(py: Python<'_>, value: &Bound<'_, PyAny>) -> Result<String, (String, pyo3::PyErr)> {
    let mut encoder: CaptureEncoder<'_> =
        CaptureEncoder::new(py).map_err(|error| (String::new(), error))?;
    let root = match encoder.encode(value) {
        Ok(root) => root,
        Err(error) => return Err((encoder.written, error)),
    };
    match encoder.document.final_chunk(&root) {
        Ok(chunk) => Ok(encoder.written + &chunk),
        Err(error) => Err((encoder.written, emit_error(error))),
    }
}

/// Write one frontier object when SQLBUILD_COMPILER_STAGE_CAPTURE_DIR names a directory.
pub(crate) fn write_stage_capture(
    stage: &Bound<'_, PyAny>,
    value: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = stage.py();
    let directory: Bound<'_, PyAny> =
        imported(py, "os", "environ")?.call_method1("get", (CAPTURE_DIR_ENV_VAR,))?;
    if !directory.is_truthy()? {
        return Ok(());
    }
    let number: u64 = imported(py, "builtins", "next")?
        .call1((imported(
            py,
            FRONTIER_CONSTANTS_MODULE,
            "STAGE_CAPTURE_SEQUENCE",
        )?,))?
        .extract()?;
    let stage_name: String = stage.getattr("value")?.str()?.extract()?;
    let path: Bound<'_, PyAny> = imported(py, "pathlib", "Path")?
        .call1((directory,))?
        .call_method1(
            "__truediv__",
            (format!("{number:03}-{stage_name}{CAPTURE_SUFFIX}"),),
        )?;
    write_capture_file(&path, value)
}

/// Write the planner's `PlanOutput` when SQLBUILD_PLANNER_CAPTURE_DIR names a directory.
pub(crate) fn write_plan_capture(plan_output: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = plan_output.py();
    let directory: Bound<'_, PyAny> =
        imported(py, "os", "environ")?.call_method1("get", (PLAN_CAPTURE_DIR_ENV_VAR,))?;
    if !directory.is_truthy()? {
        return Ok(());
    }
    let number: u64 = imported(py, "builtins", "next")?
        .call1((imported(
            py,
            FRONTIER_CONSTANTS_MODULE,
            "STAGE_CAPTURE_SEQUENCE",
        )?,))?
        .extract()?;
    let path: Bound<'_, PyAny> = imported(py, "pathlib", "Path")?
        .call1((directory,))?
        .call_method1(
            "__truediv__",
            (format!("{number:03}-{PLAN_CAPTURE_NAME}{CAPTURE_SUFFIX}"),),
        )?;
    write_capture_file(&path, plan_output)
}

/// Write the capture document of `value` to `path`, creating its directory.
fn write_capture_file(path: &Bound<'_, PyAny>, value: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = path.py();
    call_with(
        &path.getattr("parent")?.getattr("mkdir")?,
        &[
            (
                "parents",
                pyo3::types::PyBool::new(py, true).to_owned().into_any(),
            ),
            (
                "exist_ok",
                pyo3::types::PyBool::new(py, true).to_owned().into_any(),
            ),
        ],
    )?;
    let stream: Bound<'_, PyAny> = path.call_method(
        "open",
        ("w",),
        Some(&keywords(
            py,
            &[
                (
                    "encoding",
                    pyo3::types::PyString::new(py, "utf-8").into_any(),
                ),
                ("newline", pyo3::types::PyString::new(py, "\n").into_any()),
            ],
        )?),
    )?;
    within(&stream, |opened| match capture_text(py, value) {
        Ok(text) => opened.call_method1("write", (text,)).map(|_| ()),
        Err((written, error)) => {
            if !written.is_empty() {
                opened.call_method1("write", (written,))?;
            }
            Err(error)
        }
    })
}

/// Render a value as the JSON document a stage capture writes.
#[pyfunction]
fn render_stage_capture(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<String> {
    capture_text(py, value).map_err(|(_, error)| error)
}

/// Mask invocation ids, native store suffixes and refactor staging folders of a compile.
#[pyfunction]
fn mask_capture_noise(text: &str) -> String {
    masked(text)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py: Python<'_> = module.py();
    let omitted: Bound<'_, PyDict> = PyDict::new(py);
    for (type_name, names) in OMITTED_ATTRIBUTES {
        omitted.set_item(type_name, PyFrozenSet::new(py, names.iter())?)?;
    }
    module.add("STAGE_CAPTURE_OMITTED_ATTRIBUTES", omitted)?;
    module.add_function(wrap_pyfunction!(render_stage_capture, module)?)?;
    module.add_function(wrap_pyfunction!(mask_capture_noise, module)?)
}
