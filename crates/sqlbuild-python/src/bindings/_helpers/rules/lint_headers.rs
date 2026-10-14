//! Route lint bodies through the existing native declaration and header scanners.

use pyo3::prelude::{Bound, IntoPyObject, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::PyDict;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};

const NATIVE: &str = "sqlbuild._native";
const MODELS: &str = "sqlbuild.lint.models";

/// Classify a lint path, retaining the caller's supplied relative path when available.
#[pyfunction]
#[pyo3(signature = (*, file_path, project_dir, relative_path=None))]
pub(crate) fn lint_file_role<'py>(
    file_path: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
    relative_path: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = file_path.py();
    let relative = if let Some(relative) = relative_path {
        relative
    } else {
        if !file_path
            .call_method1("is_relative_to", (project_dir,))?
            .is_truthy()?
        {
            return imported(py, MODELS, "LintFileRole")?.call0();
        }
        file_path.call_method1("relative_to", (project_dir,))?
    };
    call_with(
        &imported(py, MODELS, "LintFileRole")?,
        &[
            (
                "declaration_kind",
                call_with(
                    &imported(py, NATIVE, "named_declaration_role_kind")?,
                    &[("relative_path", relative.clone())],
                )?,
            ),
            ("in_project", true.into_pyobject(py)?.to_owned().into_any()),
            (
                "in_hook_directory",
                relative.call_method1("is_relative_to", ("hooks",))?,
            ),
        ],
    )
}

/// Use audit measurement ranges when present, otherwise the native SQL header boundaries.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn lint_body_ranges<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "lint_body_ranges",
        options,
        (
            &["contents", "headers", "file_path", "project_dir"],
            &["role"],
        ),
    )?;
    let mut role = args.value("role")?;
    if role.is_none() {
        role = lint_file_role(&args.value("file_path")?, &args.value("project_dir")?, None)?;
    }
    let kind = role.getattr("declaration_kind")?;
    if role.getattr("in_project")?.is_truthy()?
        && (kind.eq("audit")? || kind.eq("singular_audit")?)
    {
        let ranges = call_with(
            &imported(py, NATIVE, "measurement_body_ranges")?,
            &[("contents", args.value("contents")?)],
        )?;
        if ranges.is_truthy()? {
            return Ok(ranges);
        }
    }
    call_with(
        &imported(py, NATIVE, "sql_body_ranges")?,
        &[
            ("contents", args.value("contents")?),
            ("headers", args.value("headers")?),
        ],
    )
}
