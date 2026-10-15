//! Native frozen value records and the field layouts they are built from.

use pyo3::exceptions::PyAttributeError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyTuple, PyType};
use pyo3::{IntoPyObjectExt, pyclass, pymethods};

use crate::bindings::_helpers::records::fields::{
    build_values, compared_values, frozen_error, record_spec, repr_text,
};

/// How a record field is filled when the caller does not pass it.
#[derive(Debug, Clone, Copy)]
pub(crate) enum FieldDefault {
    Required,
    None,
    False,
    True,
    Int(i64),
    Text(&'static str),
    EmptyTuple,
    EmptyDict,
    EmptyFrozenset,
    /// `getattr(getattr(import(module), class), member)`.
    Member(&'static str, &'static str, &'static str),
    /// `getattr(import(module), name)()`, evaluated for every instance.
    Call(&'static str, &'static str),
}

/// One record field: its name, default and whether it takes part in equality and repr.
#[derive(Debug, Clone, Copy)]
pub(crate) struct FieldSpec {
    pub(crate) name: &'static str,
    pub(crate) default: FieldDefault,
    pub(crate) compared: bool,
}

/// The layout of one native record class.
#[derive(Debug, Clone, Copy)]
pub(crate) struct RecordSpec {
    pub(crate) name: &'static str,
    pub(crate) doc: &'static str,
    pub(crate) fields: &'static [FieldSpec],
}

/// The members of one native string enum, in declaration order.
#[derive(Debug, Clone, Copy)]
pub(crate) struct EnumSpec {
    pub(crate) name: &'static str,
    pub(crate) doc: &'static str,
    pub(crate) members: &'static [(&'static str, &'static str)],
}

/// Base of every native frozen record, built, compared, shown and pickled as a dataclass.
#[derive(Debug)]
#[pyclass(module = "sqlbuild._native", subclass, frozen)]
pub(crate) struct NativeRecord {
    pub(crate) values: Vec<Py<PyAny>>,
}

#[pymethods]
impl NativeRecord {
    #[new]
    #[classmethod]
    #[pyo3(signature = (*args, **kwargs))]
    fn new(
        cls: &Bound<'_, PyType>,
        args: &Bound<'_, PyTuple>,
        kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        let spec: &RecordSpec = record_spec(cls)?;
        Ok(Self {
            values: build_values(spec, args, kwargs)?,
        })
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py: Python<'_> = slf.py();
        if !other.get_type().is(slf.get_type()) {
            return Ok(py.NotImplemented());
        }
        let other: &Bound<'_, Self> = other.cast::<Self>()?;
        compared_values(slf)?
            .as_any()
            .eq(compared_values(other)?)?
            .into_py_any(py)
    }

    fn __hash__(slf: &Bound<'_, Self>) -> PyResult<isize> {
        compared_values(slf)?.as_any().hash()
    }

    fn __repr__(slf: &Bound<'_, Self>) -> PyResult<String> {
        repr_text(slf)
    }

    fn __reduce__<'py>(slf: &Bound<'py, Self>) -> PyResult<Bound<'py, PyTuple>> {
        let py: Python<'py> = slf.py();
        let values: Bound<'py, PyTuple> = PyTuple::new(py, slf.get().values.iter())?;
        PyTuple::new(py, [slf.get_type().into_any(), values.into_any()])
    }
}

/// Read-only access to one field of a native record.
#[derive(Debug)]
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct RecordAttribute {
    pub(crate) index: usize,
    pub(crate) name: &'static str,
}

#[pymethods]
impl RecordAttribute {
    fn __get__(
        slf: &Bound<'_, Self>,
        instance: &Bound<'_, PyAny>,
        _owner: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let py: Python<'_> = slf.py();
        if instance.is_none() {
            return Ok(slf.clone().into_any().unbind());
        }
        let record: &Bound<'_, NativeRecord> = instance.cast::<NativeRecord>()?;
        let attribute: &Self = slf.get();
        record
            .get()
            .values
            .get(attribute.index)
            .map(|value| value.clone_ref(py))
            .ok_or_else(|| PyAttributeError::new_err(attribute.name))
    }

    fn __set__(&self, _instance: &Bound<'_, PyAny>, _value: &Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(_instance.py(), self.name))
    }

    fn __delete__(&self, _instance: &Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(_instance.py(), self.name))
    }
}

impl FieldSpec {
    /// A field every caller must pass.
    pub(crate) const fn required(name: &'static str) -> Self {
        Self::new(name, FieldDefault::Required)
    }

    /// A field filled from `default` when it is not passed.
    pub(crate) const fn new(name: &'static str, default: FieldDefault) -> Self {
        Self {
            name,
            default,
            compared: true,
        }
    }
}
