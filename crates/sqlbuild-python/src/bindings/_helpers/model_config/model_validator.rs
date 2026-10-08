//! The Python model validators' happy path, decided natively.

use std::collections::HashSet;

use pyo3::prelude::{Bound, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple, PyTupleMethods};
use pyo3::{pyclass, pymethods};
use sqlbuild_model_config::model_validation::main::accept_model_config::accept_model_config;
use sqlbuild_model_config::model_validation::models::{
    ModelReference, ModelValidationFacts, ProjectValidationFacts, Rejected,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;

/// Model, seed, source, function and table function names.
type ResourceNames = (
    HashSet<String>,
    HashSet<String>,
    HashSet<String>,
    HashSet<String>,
    HashSet<String>,
);

/// References, declared schema columns, unmanaged retention and declared table type.
type ModelFacts<'py> = (Bound<'py, PyTuple>, Option<Vec<String>>, bool, bool);

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
    ) -> Self {
        let (models, seeds, sources, functions, table_functions) = names;
        Self {
            project: ProjectValidationFacts {
                custom_materializations,
                microbatch_concurrency,
                models,
                seeds,
                sources,
                functions,
                table_functions,
            },
        }
    }

    /// Return whether every Python model validator accepts this model; `False` runs them.
    fn accepts(
        &self,
        values: Bound<'_, PyDict>,
        model: (String, String),
        facts: ModelFacts<'_>,
    ) -> PyResult<bool> {
        compiler_guard(|| {
            let (model_name, query_sql) = model;
            let (references, declared_columns, retention_unmanaged, table_type_declared) = facts;
            let references = references
                .iter()
                .map(|reference| {
                    Ok(ModelReference {
                        kind: reference.getattr("ref_kind")?.extract()?,
                        name: reference.getattr("ref_name")?.extract()?,
                    })
                })
                .collect::<PyResult<Vec<_>>>()?;
            let entries: Vec<(PyNode<'_>, PyNode<'_>)> = values
                .iter()
                .map(|(key, value)| (PyNode(key), PyNode(value)))
                .collect();
            let facts = ModelValidationFacts {
                model_name: &model_name,
                references: &references,
                declared_columns: declared_columns.as_deref(),
                query_sql: &query_sql,
                retention_unmanaged,
                table_type_declared,
            };
            Ok(match accept_model_config(entries, &self.project, &facts) {
                Ok(()) => true,
                Err(Rejected) => false,
            })
        })
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelValidator>()?;
    Ok(())
}
