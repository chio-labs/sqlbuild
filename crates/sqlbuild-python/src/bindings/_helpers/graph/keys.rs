//! `CompiledObjectKey`s for native `(resource type, name)` pairs, converted once per pair.

use crate::bindings::_helpers::records::construct::record_class;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};

/// One `CompiledObjectKey` per native pair, so shared keys convert once.
pub(crate) struct KeyCache<'py> {
    key_type: Bound<'py, PyAny>,
    resource_type: Bound<'py, PyAny>,
    keys: Bound<'py, PyDict>,
}

impl<'py> KeyCache<'py> {
    pub(crate) fn new(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            key_type: record_class(py, RecordId::CompiledObjectKey)?,
            resource_type: record_class(py, RecordId::CompiledResourceType)?,
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
        native_field(key, "resource_type")?.str()?.extract()?,
        native_field(key, "name")?.extract()?,
    ))
}
