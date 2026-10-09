//! The Python model validators, run natively up to the first error they raise.

use std::collections::HashSet;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{IntoPyObject, pyclass, pymethods};
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_model_config::model_validation::main::validate_model_config::validate_model_config;
use sqlbuild_model_config::model_validation::main::validate_model_references::validate_model_references;
use sqlbuild_model_config::model_validation::models::{
    ModelReference, ModelValidationFacts, ProjectValidationFacts, ValidationStop,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;

/// Model, seed, source, function and table function names.
type ResourceNames = (
    HashSet<String>,
    HashSet<String>,
    HashSet<String>,
    HashSet<String>,
    HashSet<String>,
);

/// References `(kind, name, rejected)`, schema columns, unmanaged retention and table type.
type ModelFacts = (Vec<(String, String, bool)>, Option<Vec<String>>, bool, bool);

/// The project facts every model's validation reads, captured once per compile.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelValidator {
    project: ProjectValidationFacts,
}

#[pymethods]
impl NativeModelValidator {
    #[new]
    fn new(
        names: ResourceNames,
        custom_materializations: HashSet<String>,
        microbatch_concurrency: bool,
        python: (u8, u8),
        unicode_version: &str,
    ) -> PyResult<Self> {
        let (models, seeds, sources, functions, table_functions) = names;
        let python = python_text(python, unicode_version).ok_or_else(|| {
            PyValueError::new_err(format!(
                "no Python string semantics for Python {}.{} with Unicode {unicode_version}",
                python.0, python.1
            ))
        })?;
        Ok(Self {
            project: ProjectValidationFacts {
                python,
                custom_materializations,
                microbatch_concurrency,
                models,
                seeds,
                sources,
                functions,
                table_functions,
            },
        })
    }

    /// `None` when accepted, the first error, or the first externally rejected reference.
    fn validate(
        &self,
        py: Python<'_>,
        values: Bound<'_, PyDict>,
        model: (String, String, String),
        facts: ModelFacts,
    ) -> PyResult<Py<PyAny>> {
        compiler_guard(|| {
            let (model_name, query_sql, relative_path) = model;
            let (references, declared_columns, retention_unmanaged, table_type_declared) = facts;
            let references: Vec<ModelReference> = references
                .into_iter()
                .map(|(kind, name, externally_rejected)| ModelReference {
                    kind,
                    name,
                    externally_rejected,
                })
                .collect();
            let entries: Vec<(PyNode<'_>, PyNode<'_>)> = values
                .iter()
                .map(|(key, value)| (PyNode(key), PyNode(value)))
                .collect();
            let facts = ModelValidationFacts {
                model_name: &model_name,
                relative_path: &relative_path,
                references: &references,
                declared_columns: declared_columns.as_deref(),
                query_sql: &query_sql,
                retention_unmanaged,
                table_type_declared,
            };
            match validate_model_config(entries, &self.project, &facts) {
                Ok(()) => Ok(py.None()),
                Err(stop) => stop_object(py, stop),
            }
        })
    }

    /// Check references alone: `None`, the first error, or a rejected dbt reference's index.
    fn references(
        &self,
        py: Python<'_>,
        model: (String, String),
        references: Vec<(String, String, bool)>,
    ) -> PyResult<Py<PyAny>> {
        compiler_guard(|| {
            let (model_name, relative_path) = model;
            let references: Vec<ModelReference> = references
                .into_iter()
                .map(|(kind, name, externally_rejected)| ModelReference {
                    kind,
                    name,
                    externally_rejected,
                })
                .collect();
            let facts = ModelValidationFacts {
                model_name: &model_name,
                relative_path: &relative_path,
                references: &references,
                declared_columns: None,
                query_sql: "",
                retention_unmanaged: false,
                table_type_declared: false,
            };
            match validate_model_references(&self.project, &facts) {
                Ok(()) => Ok(py.None()),
                Err(stop) => stop_object(py, stop),
            }
        })
    }
}

fn stop_object(py: Python<'_>, stop: ValidationStop) -> PyResult<Py<PyAny>> {
    match stop {
        ValidationStop::External(index) => Ok(index.into_pyobject(py)?.into_any().unbind()),
        ValidationStop::Error(error) => Ok(native_config_error(py, error)?.into_any()),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelValidator>()?;
    Ok(())
}
