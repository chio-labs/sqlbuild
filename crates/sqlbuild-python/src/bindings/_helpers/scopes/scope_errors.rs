//! Report a scope index's error findings as individual compile diagnostics.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

const COLLECTOR_MODULE: &str = "sqlbuild.compiler.compile._helpers.diagnostics.collector";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const ERROR_SEVERITY: &str = "error";

/// `report_scope_index_errors`: each error-severity finding of `index`, keyed for the collector.
pub(crate) fn report_scope_index_errors(index: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = index.py();
    let report = py
        .import(COLLECTOR_MODULE)?
        .getattr("report_compile_diagnostic")?;
    let compiler_diagnostic = py
        .import(COMPILE_MODELS_MODULE)?
        .getattr("CompilerDiagnostic")?;
    let path_class = py.import("pathlib")?.getattr("Path")?;
    for item in index.getattr("diagnostics")?.try_iter()? {
        let item: Bound<'_, PyAny> = item?;
        if item.getattr("severity")?.str()?.extract::<String>()? != ERROR_SEVERITY {
            continue;
        }
        let code: Bound<'_, PyAny> = item.getattr("code")?.getattr("value")?;
        let message: Bound<'_, PyAny> = item.getattr("message")?;
        let path: Bound<'_, PyAny> = item.getattr("path")?;
        let declaration: Bound<'_, PyAny> = item.getattr("declaration")?;
        let resource: Bound<'_, PyAny> = item.getattr("resource")?;
        let key: Bound<'_, PyTuple> = PyTuple::new(
            py,
            [
                code.clone(),
                or_empty(&path)?,
                or_empty(&declaration)?.str()?.into_any(),
                or_empty(&resource)?.str()?.into_any(),
                message.clone(),
            ],
        )?;
        let (resource_type, resource_name) = owning_resource(&resource, &declaration)?;
        let fields: Bound<'_, PyDict> = PyDict::new(py);
        fields.set_item("phase", "compile")?;
        fields.set_item("severity", ERROR_SEVERITY)?;
        fields.set_item("code", code)?;
        fields.set_item("message", message)?;
        fields.set_item("resource_type", resource_type)?;
        fields.set_item("resource_name", resource_name)?;
        if path.is_none() {
            fields.set_item("path", py.None())?;
        } else {
            fields.set_item("path", path_class.call1((path,))?)?;
        }
        fields.set_item("line", item.getattr("line")?)?;
        fields.set_item("column", item.getattr("column")?)?;
        let diagnostic: Bound<'_, PyAny> = compiler_diagnostic.call((), Some(&fields))?;
        let arguments: Bound<'_, PyDict> = PyDict::new(py);
        arguments.set_item("key", key)?;
        arguments.set_item("diagnostic", diagnostic)?;
        report.call((), Some(&arguments))?;
    }
    Ok(())
}

/// `value or ""`.
fn or_empty<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if value.is_truthy()? {
        return Ok(value.clone());
    }
    Ok(PyString::new(value.py(), "").into_any())
}

/// The compiled resource a finding names: its resource, else an audit declaration.
fn owning_resource(
    resource: &Bound<'_, PyAny>,
    declaration: &Bound<'_, PyAny>,
) -> PyResult<(Option<&'static str>, Option<String>)> {
    if !resource.is_none() {
        let kind: String = resource.getattr("kind")?.str()?.extract()?;
        let resource_type: Option<&'static str> = match kind.as_str() {
            "model" => Some("model"),
            "source" => Some("source"),
            "seed" => Some("seed"),
            "function" => Some("udf"),
            "test" => Some("sql_test"),
            "scenario" => Some("sql_scenario"),
            _ => None,
        };
        if resource_type.is_some() {
            return Ok((resource_type, Some(resource.getattr("name")?.extract()?)));
        }
    }
    if !declaration.is_none() {
        let kind: String = declaration.getattr("kind")?.str()?.extract()?;
        if matches!(kind.as_str(), "audit" | "singular_audit") {
            return Ok((Some("audit"), Some(declaration.getattr("name")?.extract()?)));
        }
    }
    Ok((None, None))
}
