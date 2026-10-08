//! `${...}` templates in authored Python config values, expanded natively.

use std::cell::RefCell;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyInt, PyList, PyListMethods, PyString,
    PyStringMethods, PyTuple, PyTupleMethods,
};
use pyo3::{FromPyObject, IntoPyObject, PyErr, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::templates::main::expand_template_string::expand_template_string;
use sqlbuild_model_config::templates::models::{
    ContextValue, Scalar, StringExpansion, TemplateFailure, TemplateOptions,
};
use sqlbuild_model_config::templates::types::TemplateHost;

const TEMPLATE_OPEN_TOKEN: &str = "${";
const ENVIRONMENT_READ: &str = "env";
const CONTEXT_READ: &str = "ctx";
const INVALID_OUTCOME: &str = "invalid";
const UNSUPPORTED_OUTCOME: &str = "unsupported";

/// Variables, the process environment and context values, all read through Python.
pub(crate) struct PythonHost<'py> {
    py: Python<'py>,
    sources: TemplateSources<'py>,
    reads: RefCell<Vec<(&'static str, String)>>,
}

impl<'py> PythonHost<'py> {
    /// Read variables, the environment and context values from these Python objects.
    pub(crate) fn new(py: Python<'py>, sources: TemplateSources<'py>) -> Self {
        Self {
            py,
            sources,
            reads: RefCell::new(Vec::new()),
        }
    }

    /// Return the `(kind, name)` reads in order.
    pub(crate) fn into_reads(self) -> Vec<(&'static str, String)> {
        self.reads.into_inner()
    }
}

/// The variables, the `os.environ` mapping and the context values one expansion reads.
#[derive(FromPyObject)]
pub(crate) struct TemplateSources<'py>(
    pub(crate) Bound<'py, PyDict>,
    pub(crate) Bound<'py, PyAny>,
    pub(crate) Bound<'py, PyDict>,
);

/// `allow_context`, `preserve_context_tokens` and `preserve_unknown_context`.
#[derive(FromPyObject)]
struct TemplateFlags(bool, bool, bool);

/// A template failure, or a Python error raised while building the expanded containers.
pub(crate) enum Stop {
    Failure(TemplateFailure),
    Python(PyErr),
}

impl From<TemplateFailure> for Stop {
    fn from(failure: TemplateFailure) -> Self {
        Self::Failure(failure)
    }
}

fn unsupported(_: PyErr) -> TemplateFailure {
    TemplateFailure::Unsupported
}

impl<'py> TemplateHost for PythonHost<'py> {
    type Value = Bound<'py, PyAny>;

    fn variable(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        self.sources.0.get_item(name).map_err(unsupported)
    }

    fn environment(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        self.reads
            .borrow_mut()
            .push((ENVIRONMENT_READ, name.to_owned()));
        let environment: &Bound<'py, PyAny> = &self.sources.1;
        if environment.contains(name).map_err(unsupported)? {
            environment.get_item(name).map(Some).map_err(unsupported)
        } else {
            Ok(None)
        }
    }

    fn context(&self, name: &str) -> Result<ContextValue<Self::Value>, TemplateFailure> {
        self.reads
            .borrow_mut()
            .push((CONTEXT_READ, name.to_owned()));
        match self.sources.2.get_item(name).map_err(unsupported)? {
            None => Ok(ContextValue::Unknown),
            Some(value) if value.is_none() => Ok(ContextValue::Unavailable),
            Some(value) => Ok(ContextValue::Value(value)),
        }
    }

    fn text(&self, text: &str) -> Result<Self::Value, TemplateFailure> {
        Ok(PyString::new(self.py, text).into_any())
    }

    fn boolean(&self, flag: bool) -> Result<Self::Value, TemplateFailure> {
        Ok(PyBool::new(self.py, flag).to_owned().into_any())
    }

    fn null(&self) -> Self::Value {
        self.py.None().into_bound(self.py)
    }

    fn scalar(&self, value: &Self::Value) -> Option<Scalar> {
        if value.is_none() {
            Some(Scalar::Null)
        } else if let Ok(flag) = value.downcast_exact::<PyBool>() {
            Some(Scalar::Bool(flag.is_true()))
        } else if value.is_exact_instance_of::<PyInt>()
            && let Ok(number) = value.extract::<i64>()
        {
            Some(Scalar::Text(number.to_string()))
        } else if let Ok(text) = value.downcast_exact::<PyString>()
            && let Ok(text) = text.to_str()
        {
            Some(Scalar::Text(text.to_owned()))
        } else {
            None
        }
    }
}

/// Return `(value, ordered reads)` as `expand_template_data` would, `invalid` or `unsupported`.
#[pyfunction]
fn expand_config_templates<'py>(
    py: Python<'py>,
    value: Bound<'py, PyAny>,
    sources: TemplateSources<'py>,
    flags: TemplateFlags,
) -> PyResult<Py<PyAny>> {
    let TemplateFlags(allow_context, preserve_context_tokens, preserve_unknown_context) = flags;
    let options = TemplateOptions {
        allow_context,
        preserve_context_tokens,
        preserve_unknown_context,
    };
    let host = PythonHost::new(py, sources);
    match expanded(&host, &value, options) {
        Ok(result) => Ok((result, host.into_reads())
            .into_pyobject(py)?
            .into_any()
            .unbind()),
        Err(Stop::Failure(TemplateFailure::Missing | TemplateFailure::Invalid)) => {
            Ok(PyString::new(py, INVALID_OUTCOME).into_any().unbind())
        }
        Err(Stop::Failure(TemplateFailure::Unsupported)) => {
            Ok(PyString::new(py, UNSUPPORTED_OUTCOME).into_any().unbind())
        }
        Err(Stop::Python(error)) => Err(error),
    }
}

pub(crate) fn expanded<'py>(
    host: &PythonHost<'py>,
    value: &Bound<'py, PyAny>,
    options: TemplateOptions,
) -> Result<Bound<'py, PyAny>, Stop> {
    let py = host.py;
    if let Ok(text) = value.downcast_exact::<PyString>() {
        let text = text.to_str().map_err(|_| TemplateFailure::Unsupported)?;
        if !text.contains(TEMPLATE_OPEN_TOKEN) {
            return Ok(value.clone());
        }
        return Ok(match expand_template_string(host, text, options)? {
            StringExpansion::Unchanged => value.clone(),
            StringExpansion::Value(result) => result,
            StringExpansion::Text(result) => PyString::new(py, &result).into_any(),
        });
    }
    if let Ok(mapping) = value.downcast_exact::<PyDict>() {
        let result = PyDict::new(py);
        for (key, item) in mapping.iter() {
            result
                .set_item(key, expanded(host, &item, options)?)
                .map_err(Stop::Python)?;
        }
        return Ok(result.into_any());
    }
    if let Ok(items) = value.downcast_exact::<PyList>() {
        let result = items
            .iter()
            .map(|item| expanded(host, &item, options))
            .collect::<Result<Vec<_>, _>>()?;
        return PyList::new(py, result)
            .map(Bound::into_any)
            .map_err(Stop::Python);
    }
    if let Ok(items) = value.downcast_exact::<PyTuple>() {
        let result = items
            .iter()
            .map(|item| expanded(host, &item, options))
            .collect::<Result<Vec<_>, _>>()?;
        return PyTuple::new(py, result)
            .map(Bound::into_any)
            .map_err(Stop::Python);
    }
    if value.is_instance_of::<PyString>()
        || value.is_instance_of::<PyDict>()
        || value.is_instance_of::<PyList>()
        || value.is_instance_of::<PyTuple>()
    {
        return Err(Stop::Failure(TemplateFailure::Unsupported));
    }
    Ok(value.clone())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(expand_config_templates, module)?)?;
    Ok(())
}
