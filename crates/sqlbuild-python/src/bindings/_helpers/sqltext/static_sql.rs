//! Interpolate `@@` tokens in authored SQL and extract static SQL references.

use std::cell::RefCell;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyListMethods, PyString, PyStringMethods};
use pyo3::{FromPyObject, PyErr, pyfunction, wrap_pyfunction};
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_sqltext::compiler::main::sql_interpolation::interpolate_sql;
use sqlbuild_sqltext::compiler::models::InterpolationRead;
use sqlbuild_sqltext::compiler::types::InterpolationHost;


const ENVIRONMENT_READ: &str = "env";
const CONTEXT_READ: &str = "ctx";

/// `(sql or None when unchanged, spans, reads, error message or None)` for one SQL text.
type InterpolationRow = (
    Option<String>,
    Vec<(usize, usize, usize, usize)>,
    Vec<(&'static str, String)>,
    Option<String>,
);

/// Project variables, the environment, context values (or `None`) and the variable renderer.
#[derive(FromPyObject)]
struct InterpolationSources<'py>(
    Bound<'py, PyDict>,
    Bound<'py, PyAny>,
    Option<Bound<'py, PyDict>>,
    Bound<'py, PyAny>,
);

struct PythonInterpolationHost<'py> {
    sources: InterpolationSources<'py>,
    /// A Python exception other than a rendering `ValueError`, raised after the scan.
    raised: RefCell<Option<PyErr>>,
}

impl PythonInterpolationHost<'_> {
    fn hold(&self, error: PyErr) -> String {
        let message = error.to_string();
        self.raised.borrow_mut().get_or_insert(error);
        message
    }

    fn text(&self, value: &Bound<'_, PyAny>) -> Result<String, String> {
        value
            .downcast::<PyString>()
            .map_err(|error| self.hold(error.into()))?
            .to_str()
            .map(str::to_owned)
            .map_err(|error| self.hold(error))
    }
}

impl InterpolationHost for PythonInterpolationHost<'_> {
    fn variable(&self, name: &str) -> Option<Result<String, String>> {
        let value = match self.sources.0.get_item(name) {
            Ok(value) => value?,
            Err(error) => return Some(Err(self.hold(error))),
        };
        if value.is_exact_instance_of::<PyString>() {
            return Some(self.text(&value));
        }
        let label = format!("SQL variable '@@{name}'");
        let py = value.py();
        let arguments = PyDict::new(py);
        if let Err(error) = arguments
            .set_item("value", value)
            .and_then(|()| arguments.set_item("label", label))
        {
            return Some(Err(self.hold(error)));
        }
        Some(match self.sources.3.call((), Some(&arguments)) {
            Ok(rendered) => self.text(&rendered),
            Err(error) if error.is_instance_of::<PyValueError>(py) => {
                Err(error.value(py).to_string())
            }
            Err(error) => Err(self.hold(error)),
        })
    }

    fn variable_names(&self) -> Vec<String> {
        let mut names: Vec<String> = self
            .sources
            .0
            .keys()
            .iter()
            .map(|key| key_text(&key))
            .collect();
        names.sort();
        names
    }

    fn environment(&self, name: &str) -> Result<Option<String>, String> {
        let environment = &self.sources.1;
        if !environment
            .contains(name)
            .map_err(|error| self.hold(error))?
        {
            return Ok(None);
        }
        let value = environment
            .get_item(name)
            .map_err(|error| self.hold(error))?;
        self.text(&value).map(Some)
    }

    fn context_allowed(&self) -> bool {
        self.sources.2.is_some()
    }

    fn context(&self, name: &str) -> Option<Option<String>> {
        let value = match self.sources.2.as_ref()?.get_item(name) {
            Ok(value) => value?,
            Err(error) => {
                let _ = self.hold(error);
                return None;
            }
        };
        if value.is_none() {
            return Some(None);
        }
        match self.text(&value) {
            Ok(text) => Some(Some(text)),
            Err(_held) => Some(None),
        }
    }

    fn context_names(&self) -> Vec<String> {
        self.sources
            .2
            .iter()
            .flat_map(|context| context.keys())
            .map(|key| key_text(&key))
            .collect()
    }
}

/// A variable or context key's text, or empty text when Python cannot render it.
fn key_text(key: &Bound<'_, PyAny>) -> String {
    key.str().map(|text| text.to_string()).unwrap_or_default()
}

/// Interpolate each `(sql, file path)`; an error is returned in its row, not raised.
#[pyfunction]
fn interpolate_sql_batch<'py>(
    sqls: Vec<(String, String)>,
    sources: InterpolationSources<'py>,
    python_version: (u8, u8),
    unicode_version: &str,
) -> PyResult<Vec<InterpolationRow>> {
    let python = python_text(python_version, unicode_version).ok_or_else(|| {
        PyRuntimeError::new_err("SQL interpolation needs a supported Python (see D017)")
    })?;
    let host = PythonInterpolationHost {
        sources,
        raised: RefCell::new(None),
    };
    let mut rows = Vec::with_capacity(sqls.len());
    for (sql, file_path) in &sqls {
        let row = match interpolate_sql(python, &host, sql, file_path) {
            Ok(result) => (result.sql, result.spans, read_rows(result.reads), None),
            Err(failure) => (
                None,
                Vec::new(),
                read_rows(failure.reads),
                Some(failure.message),
            ),
        };
        if let Some(error) = host.raised.borrow_mut().take() {
            return Err(error);
        }
        rows.push(row);
    }
    Ok(rows)
}

fn read_rows(reads: Vec<InterpolationRead>) -> Vec<(&'static str, String)> {
    reads
        .into_iter()
        .map(|read| match read {
            InterpolationRead::Environment(name) => (ENVIRONMENT_READ, name),
            InterpolationRead::Context(name) => (CONTEXT_READ, name),
        })
        .collect()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(interpolate_sql_batch, module)?)?;
    Ok(())
}
