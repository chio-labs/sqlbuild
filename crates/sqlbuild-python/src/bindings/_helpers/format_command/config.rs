//! The run's `LintConfig`, resolved from the project's configuration files.

use std::path::Path;

use pyo3::IntoPyObject;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyString;
use sqlbuild_rules::lint_text::main::resolve_format_settings::resolve_format_settings;
use sqlbuild_rules::lint_text::models::FormatSettings;

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

/// Format settings and whether lint suppressions are allowed.
pub(crate) struct FormatConfig {
    pub(crate) settings: FormatSettings,
    pub(crate) allow_suppressions: bool,
}

/// Resolve the settings, loading the rules configuration when the project file exists.
pub(crate) fn format_config(
    py: Python<'_>,
    project_dir: &Bound<'_, PyAny>,
) -> PyResult<FormatConfig> {
    let directory: std::path::PathBuf = project_dir.extract()?;
    let settings: FormatSettings =
        resolve_format_settings(Path::new(&directory)).map_err(PyValueError::new_err)?;
    let allow_suppressions: bool = if settings.has_project_config {
        call_with(
            &registry::native(py, NativeAttr::LoadRulesConfig)?,
            &[("project_dir", project_dir.call_method0("resolve")?)],
        )?
        .getattr("allow_exceptions")?
        .extract()?
    } else {
        true
    };
    Ok(FormatConfig {
        settings,
        allow_suppressions,
    })
}

/// The Python `LintConfig` of `config`, linting as `dialect`.
pub(crate) fn lint_config<'py>(
    py: Python<'py>,
    config: &FormatConfig,
    dialect: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let settings: &FormatSettings = &config.settings;
    call_with(
        &registry::class(py, RecordId::LintConfig)?,
        &[
            (
                "line_width",
                settings.line_width.into_pyobject(py)?.into_any(),
            ),
            (
                "max_description_lines",
                settings.max_description_lines.into_pyobject(py)?.into_any(),
            ),
            ("dialect", PyString::new(py, dialect).into_any()),
            (
                "max_literal_length",
                settings.max_literal_length.into_pyobject(py)?.into_any(),
            ),
            (
                "max_ranking_order_by",
                settings.max_ranking_order_by.into_pyobject(py)?.into_any(),
            ),
            (
                "allow_suppressions",
                pyo3::types::PyBool::new(py, config.allow_suppressions)
                    .to_owned()
                    .into_any(),
            ),
        ],
    )
}
