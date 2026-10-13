//! `CompiledObjectKey`s for native `(resource type, name)` pairs, converted once per pair.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";

/// One `CompiledObjectKey` per native pair, so shared keys convert once.
pub(crate) struct KeyCache<'py> {
    key_type: Bound<'py, PyAny>,
    resource_type: Bound<'py, PyAny>,
    keys: Bound<'py, PyDict>,
}

impl<'py> KeyCache<'py> {
    pub(crate) fn new(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            key_type: py
                .import(COMPILE_MODELS_MODULE)?
                .getattr("CompiledObjectKey")?,
            resource_type: py
                .import(COMPILE_TYPES_MODULE)?
                .getattr("CompiledResourceType")?,
            keys: PyDict::new(py),
        })
    }

    pub(crate) fn py(&self) -> Python<'py> {
        self.keys.py()
    }

    /// The `CompiledObjectKey` for one `(resource type, name)` pair.
    pub(crate) fn key(
        &self,
        (resource_type, name): &(String, String),
    ) -> PyResult<Bound<'py, PyAny>> {
        let pair = (resource_type.as_str(), name.as_str());
        if let Some(existing) = self.keys.get_item(pair)? {
            return Ok(existing);
        }
        let keywords: Bound<'py, PyDict> = PyDict::new(self.keys.py());
        keywords.set_item("resource_type", self.resource_type.call1((resource_type,))?)?;
        keywords.set_item("name", name)?;
        let created: Bound<'py, PyAny> = self.key_type.call((), Some(&keywords))?;
        self.keys.set_item(pair, &created)?;
        Ok(created)
    }

    /// `CompiledObjectKey`s for `pairs`, in order.
    pub(crate) fn keys(&self, pairs: &[(String, String)]) -> PyResult<Vec<Bound<'py, PyAny>>> {
        pairs.iter().map(|pair| self.key(pair)).collect()
    }
}

/// The native `(resource type, name)` pair of a `CompiledObjectKey`.
pub(crate) fn native_key(key: &Bound<'_, PyAny>) -> PyResult<(String, String)> {
    Ok((
        key.getattr("resource_type")?.str()?.extract()?,
        key.getattr("name")?.extract()?,
    ))
}
