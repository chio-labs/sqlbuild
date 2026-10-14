//! The SQL expansion context compiler-integrated lint expands authored bodies with.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_attachment::sql_expansion_context::build_sql_expansion_context;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const RESOLVE_ADAPTER_MODULE: &str = "sqlbuild.adapter.discovery.main.resolve_adapter";
const ADAPTER_EXCEPTIONS_MODULE: &str = "sqlbuild.adapter.contract.exceptions";
const COMPILE_EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const DISCOVERY_EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.discovery.exceptions";
const LINT_EXCEPTIONS_MODULE: &str = "sqlbuild.lint.exceptions";
const COMPILE_FIRST_MESSAGE: &str = "compiler-integrated Rules check the SQL your project \
    actually produces, so the project must compile first";

/// Build the lint expansion context, reporting compile failures as `ProjectCompileError`.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_lint_expansion_context<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_lint_expansion_context",
        options,
        (
            &["project_dir"],
            &[
                "value_renderer",
                "discovered_inputs",
                "declaration_scope",
                "static_declaration_scope",
            ],
        ),
    )?;
    expansion_context(py, &arguments).or_else(|error| Err(compile_first_error(py, error)?))
}

fn expansion_context<'py>(
    py: Python<'py>,
    arguments: &KeywordArguments<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let project_dir: Bound<'py, PyAny> = arguments.value("project_dir")?;
    let mut discovered: Bound<'py, PyAny> = arguments.value("discovered_inputs")?;
    if discovered.is_none() {
        let no: Bound<'py, PyAny> = PyBool::new(py, false).to_owned().into_any();
        discovered = call_with(
            &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
            &[
                ("project_dir", project_dir.clone()),
                ("sql_analysis_enabled_override", no.clone()),
                ("extract_output_column_locations", no),
            ],
        )?;
    }
    let mut renderer: Bound<'py, PyAny> = arguments.value("value_renderer")?;
    if !renderer.is_truthy()? {
        let adapter_name: Bound<'py, PyAny> = call_with(
            &imported(py, NATIVE_MODULE, "resolve_effective_adapter_name")?,
            &[
                ("project_config", discovered.getattr("project_config")?),
                ("local_config", discovered.getattr("local_config")?),
            ],
        )?;
        renderer = call_with(
            &imported(py, RESOLVE_ADAPTER_MODULE, "resolve_adapter")?,
            &[
                ("adapter_name", adapter_name),
                ("project_dir", project_dir.clone()),
            ],
        )?;
    }
    build_sql_expansion_context(
        py,
        Some(keywords(
            py,
            &[
                ("project_dir", project_dir),
                ("discovered_inputs", discovered),
                ("value_renderer", renderer),
                ("declaration_scope", arguments.value("declaration_scope")?),
                (
                    "static_declaration_scope",
                    arguments.value("static_declaration_scope")?,
                ),
            ],
        )?),
    )
}

/// Adapter, compile and discovery errors as `ProjectCompileError`; any other error unchanged.
fn compile_first_error(py: Python<'_>, error: PyErr) -> PyResult<PyErr> {
    let value: Bound<'_, PyAny> = error.value(py).clone().into_any();
    let reported: bool = value.is_instance(&imported(
        py,
        ADAPTER_EXCEPTIONS_MODULE,
        "AdapterUserError",
    )?)? || value.is_instance(&imported(
        py,
        COMPILE_EXCEPTIONS_MODULE,
        "CompileInputError",
    )?)? || value.is_instance(&imported(
        py,
        DISCOVERY_EXCEPTIONS_MODULE,
        "DiscoveryError",
    )?)?;
    if !reported {
        return Ok(error);
    }
    let message: String = format!("{COMPILE_FIRST_MESSAGE}: {}", value.str()?);
    let raised: PyErr = PyErr::from_value(
        imported(py, LINT_EXCEPTIONS_MODULE, "ProjectCompileError")?.call1((message,))?,
    );
    raised.set_cause(py, Some(error));
    Ok(raised)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_lint_expansion_context, module)?)
}
