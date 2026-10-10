//! `${...}` templates in authored Python config values and effective vars, expanded natively.

use std::cell::RefCell;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyStringMethods,
    PyTuple, PyTupleMethods,
};
use pyo3::{FromPyObject, IntoPyObject, PyErr, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::templates::errors::TemplateError;
use sqlbuild_model_config::templates::main::expand_template_string::expand_template_string;
use sqlbuild_model_config::templates::main::expand_template_text::expand_template_text;
use sqlbuild_model_config::templates::main::template_error_message::template_error_message;
use sqlbuild_model_config::templates::models::{
    ContextValue, Scalar, StringExpansion, TemplateFailure, TemplateOptions,
};
use sqlbuild_model_config::templates::types::TemplateHost;

use crate::bindings::_helpers::model_config::config_errors::native_config_error;

const TEMPLATE_OPEN_TOKEN: &str = "${";
const ENVIRONMENT_READ: &str = "env";
const CONTEXT_READ: &str = "ctx";
const EFFECTIVE_VARS_LABEL: &str = "effective vars";
const PROJECT_VAR_VALUES_MODULE: &str =
    "sqlbuild.compiler.authored_values.main._project_var_values";
const RENDER_PROJECT_VAR_TEXT: &str = "render_project_var_text";

/// Variables, the process environment and context values, all read through Python.
pub(crate) struct PythonHost<'py> {
    py: Python<'py>,
    sources: TemplateSources<'py>,
    label: String,
    effective: Option<EffectiveVars<'py>>,
    reads: RefCell<Vec<(&'static str, String)>>,
    raised: RefCell<Option<PyErr>>,
}

/// Effective vars resolved on demand, as Python's `_EffectiveVarsResolver` resolves them.
struct EffectiveVars<'py> {
    resolved: Bound<'py, PyDict>,
    resolving: RefCell<Vec<String>>,
}

impl<'py> PythonHost<'py> {
    /// Read variables, the environment and context values from these Python objects.
    pub(crate) fn new(py: Python<'py>, sources: TemplateSources<'py>, label: &str) -> Self {
        Self {
            py,
            sources,
            label: label.to_owned(),
            effective: None,
            reads: RefCell::new(Vec::new()),
            raised: RefCell::new(None),
        }
    }

    /// Return the `(kind, name)` reads in order.
    pub(crate) fn into_reads(self) -> Vec<(&'static str, String)> {
        self.reads.into_inner()
    }

    /// Hold a Python error until the expansion returns, and stop evaluation.
    fn hold(&self, error: PyErr) -> TemplateFailure {
        self.raised.borrow_mut().get_or_insert(error);
        TemplateFailure::Host
    }

    /// The stop for `failure`, taking the held Python error of a host failure.
    pub(crate) fn stop(&self, failure: TemplateFailure) -> Stop {
        match failure {
            TemplateFailure::Missing(error) | TemplateFailure::Invalid(error) => {
                Stop::Failure(error)
            }
            TemplateFailure::Host => {
                Stop::Python(self.raised.borrow_mut().take().unwrap_or_else(|| {
                    PyRuntimeError::new_err("template expansion stopped without an error")
                }))
            }
        }
    }

    fn text_of(&self, value: &Bound<'py, PyAny>) -> Result<String, TemplateFailure> {
        value
            .downcast::<PyString>()
            .map_err(|error| self.hold(error.into()))?
            .to_str()
            .map(str::to_owned)
            .map_err(|error| self.hold(error))
    }

    /// Resolve effective var `name`, keeping Python's resolving stack on errors.
    fn resolve(
        &self,
        effective: &EffectiveVars<'py>,
        name: &str,
    ) -> Result<Option<Bound<'py, PyAny>>, TemplateFailure> {
        let Some(raw) = self
            .sources
            .0
            .get_item(name)
            .map_err(|error| self.hold(error))?
        else {
            return Ok(None);
        };
        if let Some(value) = effective
            .resolved
            .get_item(name)
            .map_err(|error| self.hold(error))?
        {
            return Ok(Some(value));
        }
        if effective.resolving.borrow().iter().any(|key| key == name) {
            let mut cycle = effective.resolving.borrow().clone();
            cycle.push(name.to_owned());
            return Err(TemplateFailure::Invalid(TemplateError::Message(format!(
                "{EFFECTIVE_VARS_LABEL} contain a cyclic reference: {}",
                cycle.join(" -> ")
            ))));
        }
        effective.resolving.borrow_mut().push(name.to_owned());
        let value = if raw.is_instance_of::<PyString>() {
            let text = self.text_of(&raw)?;
            let options = TemplateOptions {
                allow_context: false,
                preserve_context_tokens: false,
                preserve_unknown_context: false,
            };
            PyString::new(self.py, &expand_template_text(self, &text, options)?).into_any()
        } else {
            raw
        };
        effective.resolving.borrow_mut().pop();
        effective
            .resolved
            .set_item(name, &value)
            .map_err(|error| self.hold(error))?;
        Ok(Some(value))
    }
}

/// The variables, the `os.environ` mapping and the context values one expansion reads.
#[derive(FromPyObject)]
pub(crate) struct TemplateSources<'py>(
    pub(crate) Bound<'py, PyDict>,
    pub(crate) Bound<'py, PyAny>,
    pub(crate) Bound<'py, PyDict>,
);

/// `allow_context`, `preserve_context_tokens`, `preserve_unknown_context` and the context label.
#[derive(FromPyObject)]
struct TemplateFlags(bool, bool, bool, String);

/// A template error, or a Python error raised while reading values or building containers.
pub(crate) enum Stop {
    Failure(TemplateError),
    Python(PyErr),
}

/// The `CompileInputError` Python raises for a template error in the context `label`.
pub(crate) fn template_error(error: &TemplateError, label: &str) -> ConfigError {
    ConfigError::compile(template_error_message(error, label))
}

impl<'py> TemplateHost for PythonHost<'py> {
    type Value = Bound<'py, PyAny>;

    fn variable(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        if let Some(effective) = &self.effective {
            return self.resolve(effective, name);
        }
        self.sources
            .0
            .get_item(name)
            .map_err(|error| self.hold(error))
    }

    fn environment(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        self.reads
            .borrow_mut()
            .push((ENVIRONMENT_READ, name.to_owned()));
        let environment: &Bound<'py, PyAny> = &self.sources.1;
        if environment
            .contains(name)
            .map_err(|error| self.hold(error))?
        {
            environment
                .get_item(name)
                .map(Some)
                .map_err(|error| self.hold(error))
        } else {
            Ok(None)
        }
    }

    fn context(&self, name: &str) -> Result<ContextValue<Self::Value>, TemplateFailure> {
        self.reads
            .borrow_mut()
            .push((CONTEXT_READ, name.to_owned()));
        match self
            .sources
            .2
            .get_item(name)
            .map_err(|error| self.hold(error))?
        {
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

    fn scalar(&self, value: &Self::Value) -> Result<Scalar, TemplateFailure> {
        if value.is_none() {
            return Ok(Scalar::Null);
        }
        if let Ok(flag) = value.downcast_exact::<PyBool>() {
            return Ok(Scalar::Bool(flag.is_true()));
        }
        let text = value.str().map_err(|error| self.hold(error))?;
        self.text_of(text.as_any()).map(Scalar::Text)
    }

    fn render(&self, value: &Self::Value, label: &str) -> Result<String, TemplateFailure> {
        if value.is_exact_instance_of::<PyString>() {
            return self.text_of(value);
        }
        let rendered = self
            .py
            .import(PROJECT_VAR_VALUES_MODULE)
            .and_then(|module| module.getattr(RENDER_PROJECT_VAR_TEXT))
            .and_then(|render| {
                let arguments = PyDict::new(self.py);
                arguments.set_item("value", value)?;
                arguments.set_item("label", label)?;
                render.call((), Some(&arguments))
            });
        match rendered {
            Ok(text) => self.text_of(&text),
            Err(error) if error.is_instance_of::<PyValueError>(self.py) => Err(
                TemplateFailure::Invalid(TemplateError::Message(error.value(self.py).to_string())),
            ),
            Err(error) => Err(self.hold(error)),
        }
    }

    fn label(&self) -> &str {
        &self.label
    }
}

/// Return `(value, reads)` as `expand_template_data` would, or `(error, reads)`.
#[pyfunction]
fn expand_config_templates<'py>(
    py: Python<'py>,
    value: Bound<'py, PyAny>,
    sources: TemplateSources<'py>,
    flags: TemplateFlags,
) -> PyResult<Py<PyAny>> {
    let TemplateFlags(allow_context, preserve_context_tokens, preserve_unknown_context, label) =
        flags;
    let options = TemplateOptions {
        allow_context,
        preserve_context_tokens,
        preserve_unknown_context,
    };
    let host = PythonHost::new(py, sources, &label);
    let result = expanded(&host, &value, options);
    outcome(py, host, result, &label)
}

/// Return `(resolved vars, reads)` as `expand_effective_vars` would, or `(error, reads)`.
#[pyfunction]
fn expand_effective_vars<'py>(
    py: Python<'py>,
    raw_values: Bound<'py, PyDict>,
    environment: Bound<'py, PyAny>,
) -> PyResult<Py<PyAny>> {
    let mut host = PythonHost::new(
        py,
        TemplateSources(raw_values.clone(), environment, PyDict::new(py)),
        EFFECTIVE_VARS_LABEL,
    );
    let resolved = PyDict::new(py);
    host.effective = Some(EffectiveVars {
        resolved: resolved.clone(),
        resolving: RefCell::new(Vec::new()),
    });
    let mut result: Result<Bound<'py, PyAny>, Stop> = Ok(resolved.clone().into_any());
    for key in raw_values.keys() {
        let name = key.str()?.to_str()?.to_owned();
        if let Err(failure) = host.variable(&name) {
            result = Err(host.stop(failure));
            break;
        }
    }
    outcome(py, host, result, EFFECTIVE_VARS_LABEL)
}

fn outcome<'py>(
    py: Python<'py>,
    host: PythonHost<'py>,
    result: Result<Bound<'py, PyAny>, Stop>,
    label: &str,
) -> PyResult<Py<PyAny>> {
    let value = match result {
        Ok(value) => value,
        Err(Stop::Failure(error)) => native_config_error(py, template_error(&error, label))?
            .into_pyobject(py)?
            .into_any(),
        Err(Stop::Python(error)) => return Err(error),
    };
    Ok((value, host.into_reads())
        .into_pyobject(py)?
        .into_any()
        .unbind())
}

/// Expand every template in `value` and the containers inside it.
pub(crate) fn expanded<'py>(
    host: &PythonHost<'py>,
    value: &Bound<'py, PyAny>,
    options: TemplateOptions,
) -> Result<Bound<'py, PyAny>, Stop> {
    let py = host.py;
    if let Ok(text) = value.downcast::<PyString>() {
        let text = text.to_str().map_err(Stop::Python)?;
        if !text.contains(TEMPLATE_OPEN_TOKEN) {
            return Ok(value.clone());
        }
        return match expand_template_string(host, text, options) {
            Ok(StringExpansion::Unchanged) => Ok(PyString::new(py, text).into_any()),
            Ok(StringExpansion::Value(result)) => Ok(result),
            Ok(StringExpansion::Text(result)) => Ok(PyString::new(py, &result).into_any()),
            Err(failure) => Err(host.stop(failure)),
        };
    }
    if let Ok(mapping) = value.downcast::<PyDict>() {
        let result = PyDict::new(py);
        for (key, item) in mapping.iter() {
            result
                .set_item(key, expanded(host, &item, options)?)
                .map_err(Stop::Python)?;
        }
        return Ok(result.into_any());
    }
    if let Ok(items) = value.downcast::<PyList>() {
        let result = items
            .iter()
            .map(|item| expanded(host, &item, options))
            .collect::<Result<Vec<_>, _>>()?;
        return PyList::new(py, result)
            .map(Bound::into_any)
            .map_err(Stop::Python);
    }
    if let Ok(items) = value.downcast::<PyTuple>() {
        let result = items
            .iter()
            .map(|item| expanded(host, &item, options))
            .collect::<Result<Vec<_>, _>>()?;
        return PyTuple::new(py, result)
            .map(Bound::into_any)
            .map_err(Stop::Python);
    }
    Ok(value.clone())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(expand_config_templates, module)?)?;
    module.add_function(wrap_pyfunction!(expand_effective_vars, module)?)?;
    Ok(())
}
