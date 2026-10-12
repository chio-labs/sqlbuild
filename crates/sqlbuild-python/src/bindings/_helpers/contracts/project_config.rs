//! Load the project and local configuration files into their Python config objects.

use std::path::PathBuf;

use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBytes, PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_config::project::errors::{ConfigFailure, FailureClass, LoadFailure};
use sqlbuild_config::project::main::load_local_config::load_local_config;
use sqlbuild_config::project::main::load_project_config::load_project_config;
use sqlbuild_config::project::main::local_sql_analysis_failure::local_sql_analysis_failure;
use sqlbuild_config::project::main::resolve_config_file::resolve_config_file;
use sqlbuild_config::project::models::{Built, ConfigFile, ConfigPaths};

use crate::bindings::_helpers::boundary::config_values::config_value_to_python;

const MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";
const ERRORS_MODULE: &str = "sqlbuild.compiler.discovery.exceptions";
const PROJECT_CONFIG_ERROR: &str = "ProjectConfigError";
const FILE_NAMES: [&str; 4] = [
    "sqlbuild_project.toml",
    "sqlbuild_project.yml",
    "sqlbuild_local.toml",
    "sqlbuild_local.yml",
];
/// The module of each `StrEnum` a loaded config holds.
const ENUM_MODULES: [(&str, &str); 10] = [
    ("ColumnContractMode", "sqlbuild.spec.contracts.types"),
    ("FutureCursorAction", "sqlbuild.spec.contracts.types"),
    ("MicrobatchLimitAction", "sqlbuild.spec.contracts.types"),
    ("TableType", "sqlbuild.spec.contracts.types"),
    ("TableTypeDowngradePolicy", "sqlbuild.spec.contracts.types"),
    ("RetentionDecreasePolicy", "sqlbuild.spec.contracts.types"),
    (
        "MissingMigrationOriginPolicy",
        "sqlbuild.spec.contracts.types",
    ),
    ("EventExportSeverity", "sqlbuild.spec.contracts.types"),
    ("AuditSeverity", "sqlbuild.compiler.auditing.types"),
    ("CollectionRendering", "sqlbuild.sql_values.types"),
];

/// The four configuration file paths of a project directory, as Python and native paths.
struct Files<'py> {
    python: Vec<Bound<'py, PyAny>>,
    native: ConfigPaths,
}

fn files<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Files<'py>> {
    let python = FILE_NAMES
        .iter()
        .map(|name| project_dir.call_method1("__truediv__", (*name,)))
        .collect::<PyResult<Vec<_>>>()?;
    let native: Vec<PathBuf> = python
        .iter()
        .map(pyo3::types::PyAnyMethods::extract::<PathBuf>)
        .collect::<PyResult<_>>()?;
    let [project, legacy_project, local, legacy_local]: [PathBuf; 4] = native
        .try_into()
        .map_err(|_| PyOSError::new_err("configuration paths"))?;
    Ok(Files {
        python,
        native: ConfigPaths {
            project,
            legacy_project,
            local,
            legacy_local,
        },
    })
}

fn file_index(file: ConfigFile) -> usize {
    match file {
        ConfigFile::Project => 0,
        ConfigFile::LegacyProject => 1,
        ConfigFile::Local => 2,
        ConfigFile::LegacyLocal => 3,
    }
}

fn config_error(py: Python<'_>, failure: &ConfigFailure, files: &Files<'_>) -> PyResult<PyErr> {
    use sqlbuild_config::project::errors::MessagePiece;
    let pieces = failure
        .message
        .iter()
        .map(|piece| match piece {
            MessagePiece::Text(text) => Ok(PyString::new(py, text).into_any()),
            MessagePiece::File(file) => files.python[file_index(*file)].str().map(Bound::into_any),
        })
        .collect::<PyResult<Vec<_>>>()?;
    let message = PyString::new(py, "").call_method1("join", (pieces,))?;
    if failure.class == FailureClass::IntegerDigits {
        return Ok(PyValueError::new_err(message.unbind()));
    }
    let keywords = PyDict::new(py);
    keywords.set_item("help", failure.help.as_deref())?;
    let error = py
        .import(ERRORS_MODULE)?
        .getattr(PROJECT_CONFIG_ERROR)?
        .call((message,), Some(&keywords))?;
    Ok(PyErr::from_value(error))
}

fn os_error(py: Python<'_>, error: &std::io::Error, path: &Bound<'_, PyAny>) -> PyResult<PyErr> {
    let Some(errno) = error.raw_os_error() else {
        return Ok(PyOSError::new_err(error.to_string()));
    };
    let reason = py.import("os")?.call_method1("strerror", (errno,))?;
    let value = py
        .import("builtins")?
        .getattr("OSError")?
        .call1((errno, reason, path.str()?))?;
    Ok(PyErr::from_value(value))
}

fn load_error(py: Python<'_>, failure: &LoadFailure, files: &Files<'_>) -> PyResult<PyErr> {
    match failure {
        LoadFailure::Config(failure) => config_error(py, failure, files),
        LoadFailure::Io(file, error) => os_error(py, error, &files.python[file_index(*file)]),
        LoadFailure::Utf8(bytes) => Ok(PyBytes::new(py, bytes)
            .call_method0("decode")
            .err()
            .unwrap_or_else(|| PyOSError::new_err("invalid UTF-8"))),
    }
}

fn enum_member<'py>(py: Python<'py>, class: &str, value: &str) -> PyResult<Bound<'py, PyAny>> {
    let module = ENUM_MODULES
        .iter()
        .find(|(name, _)| *name == class)
        .map_or("sqlbuild.spec.contracts.types", |(_, module)| *module);
    py.import(module)?.getattr(class)?.call1((value,))
}

fn object<'py>(
    py: Python<'py>,
    class: &str,
    fields: Vec<(&'static str, Built)>,
) -> PyResult<Bound<'py, PyAny>> {
    let keywords = PyDict::new(py);
    for (name, value) in fields {
        keywords.set_item(name, built(py, value)?)?;
    }
    py.import(MODELS_MODULE)?
        .getattr(class)?
        .call((), Some(&keywords))
}

fn built(py: Python<'_>, value: Built) -> PyResult<Py<PyAny>> {
    match value {
        Built::Value(value) => config_value_to_python(py, value),
        Built::Object(class, fields) => Ok(object(py, class, fields)?.unbind()),
        Built::Enum(class, member) => Ok(enum_member(py, class, &member)?.unbind()),
        Built::Dict(entries) => {
            let mapping = PyDict::new(py);
            for (key, item) in entries {
                mapping.set_item(key, built(py, item)?)?;
            }
            Ok(mapping.into_any().unbind())
        }
        Built::Tuple(items) => PyTuple::new(py, items)?.into_py_any(py),
        Built::FrozenSet(items) => PyFrozenSet::new(py, items)?.into_py_any(py),
        Built::Decimal(value) => {
            let number = config_value_to_python(py, value)?;
            let text = number.bind(py).str()?;
            Ok(py
                .import("decimal")?
                .getattr("Decimal")?
                .call1((text,))?
                .unbind())
        }
    }
}

/// `load_project_config`: the validated `ProjectConfig` of `project_dir`.
#[pyfunction]
fn load_project_config_file(py: Python<'_>, project_dir: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let files = files(project_dir)?;
    match load_project_config(&files.native) {
        Ok(config) => built(py, config),
        Err(failure) => Err(load_error(py, &failure, &files)?),
    }
}

/// `load_local_config`: the validated `LocalConfig` of `project_dir`, or the default.
#[pyfunction]
fn load_local_config_file(py: Python<'_>, project_dir: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let files = files(project_dir)?;
    match load_local_config(&files.native) {
        Ok(config) => built(py, config),
        Err(failure) => Err(load_error(py, &failure, &files)?),
    }
}

/// The project or local configuration file path, rejecting an unconverted legacy file.
#[pyfunction]
fn resolve_config_file_path<'py>(
    py: Python<'py>,
    project_dir: &Bound<'py, PyAny>,
    local: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let files = files(project_dir)?;
    match resolve_config_file(&files.native, local) {
        Ok(file) => Ok(files.python[file_index(file)].clone()),
        Err(failure) => Err(config_error(py, &failure, &files)?),
    }
}

/// `validate_local_sql_analysis_policy` from the project requirement and the local setting.
#[pyfunction]
fn validate_local_sql_analysis(
    py: Python<'_>,
    project_dir: &Bound<'_, PyAny>,
    flags: (bool, bool, bool),
) -> Result<(), PyErr> {
    let files = files(project_dir)?;
    match local_sql_analysis_failure(&files.native, flags) {
        None => Ok(()),
        Some(failure) => Err(config_error(py, &failure, &files)?),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(load_project_config_file, module)?)?;
    module.add_function(wrap_pyfunction!(load_local_config_file, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_config_file_path, module)?)?;
    module.add_function(wrap_pyfunction!(validate_local_sql_analysis, module)?)
}
