//! Semantic styling for human CLI output, as a Python class.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyclass, pymethods};
use sqlbuild_core::cli_text::models::CliStyle as NativeStyle;

/// Semantic CLI styling facade used by human-output formatters.
#[pyclass(name = "CliStyle", module = "sqlbuild._native", frozen)]
pub(crate) struct PythonCliStyle {
    #[pyo3(get)]
    pub(crate) use_color: bool,
}

impl PythonCliStyle {
    fn native(&self) -> NativeStyle {
        NativeStyle {
            use_color: self.use_color,
        }
    }
}

#[pymethods]
impl PythonCliStyle {
    #[new]
    #[pyo3(signature = (*, use_color))]
    pub(crate) fn new(use_color: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            use_color: use_color.is_truthy()?,
        })
    }

    fn title(&self, text: &str) -> String {
        self.native().title(text)
    }

    fn section(&self, text: &str) -> String {
        self.native().section(text)
    }

    fn label(&self, text: &str) -> String {
        self.native().label(text)
    }

    fn value(&self, text: &str) -> String {
        self.native().value(text)
    }

    fn accent(&self, text: &str) -> String {
        self.native().accent(text)
    }

    fn accent_strong(&self, text: &str) -> String {
        self.native().accent_strong(text)
    }

    fn plan_section(&self, text: &str) -> String {
        self.native().plan_section(text)
    }

    fn object_name(&self, text: &str) -> String {
        self.native().object_name(text)
    }

    fn command(&self, text: &str) -> String {
        self.native().command(text)
    }

    fn muted(&self, text: &str) -> String {
        self.native().muted(text)
    }

    fn success(&self, text: &str) -> String {
        self.native().success(text)
    }

    fn success_strong(&self, text: &str) -> String {
        self.native().success_strong(text)
    }

    fn warning(&self, text: &str) -> String {
        self.native().warning(text)
    }

    fn warning_strong(&self, text: &str) -> String {
        self.native().warning_strong(text)
    }

    fn error(&self, text: &str) -> String {
        self.native().error(text)
    }

    fn error_strong(&self, text: &str) -> String {
        self.native().error_strong(text)
    }

    fn error_muted(&self, text: &str) -> String {
        self.native().error_muted(text)
    }

    fn log_label(&self, text: &str) -> String {
        self.native().log_label(text)
    }

    fn dbt_section(&self, text: &str) -> String {
        self.native().dbt_section(text)
    }

    fn dbt_label(&self, text: &str) -> String {
        self.native().dbt_label(text)
    }

    fn dbt_object_name(&self, text: &str) -> String {
        self.native().dbt_object_name(text)
    }

    fn dbt_execution_label(&self, text: &str) -> String {
        self.native().dbt_execution_label(text)
    }

    /// Style status text according to the status word.
    #[pyo3(signature = (*, status, text = None))]
    fn status(&self, status: &str, text: Option<&str>) -> String {
        self.native().status_text(status, text.unwrap_or(status))
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PythonCliStyle>()
}
