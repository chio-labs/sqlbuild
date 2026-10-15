//! Construction, comparison and display of native record field values.

use pyo3::IntoPyObjectExt;
use pyo3::exceptions::{PyAttributeError, PyTypeError};
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::pyclass::CompareOp;
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple, PyTupleMethods, PyType,
    PyTypeMethods,
};

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::records::constants::{
    FROZEN_INSTANCE_ERROR, ORDERED_RECORDS, RECORD_FINISHERS, RECORD_SPEC_ATTRIBUTE, RECORDS,
};
use crate::bindings::_helpers::records::models::{FieldDefault, NativeRecord, RecordSpec};

/// Every registered record spec, in registration order.
pub(crate) fn all_specs() -> impl Iterator<Item = &'static RecordSpec> {
    RECORDS.iter().flat_map(|group| group.iter())
}

/// The spec registered for `cls`, read from its class attribute.
pub(crate) fn record_spec(cls: &Bound<'_, PyType>) -> PyResult<&'static RecordSpec> {
    let Ok(index) = cls.getattr(RECORD_SPEC_ATTRIBUTE) else {
        return Err(PyTypeError::new_err(format!(
            "{} cannot be instantiated directly",
            cls.qualname()?
        )));
    };
    let index: usize = index.extract()?;
    all_specs()
        .nth(index)
        .ok_or_else(|| PyTypeError::new_err("unknown native record class"))
}

/// Field values bound from `args` and `kwargs` as a dataclass `__init__` binds them.
pub(crate) fn build_values(
    spec: &RecordSpec,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Vec<Py<PyAny>>> {
    let py: Python<'_> = args.py();
    let name: &str = spec.name;
    if args.len() > spec.fields.len() {
        return Err(PyTypeError::new_err(format!(
            "{name}.__init__() takes {} positional arguments but {} were given",
            spec.fields.len() + 1,
            args.len() + 1
        )));
    }
    if let Some(kwargs) = kwargs {
        for key in kwargs.keys() {
            let key: String = key.extract()?;
            if !spec.fields.iter().any(|field| field.name == key) {
                return Err(PyTypeError::new_err(format!(
                    "{name}.__init__() got an unexpected keyword argument '{key}'"
                )));
            }
        }
    }
    let mut values: Vec<Py<PyAny>> = Vec::with_capacity(spec.fields.len());
    for (index, field) in spec.fields.iter().enumerate() {
        let keyword: Option<Bound<'_, PyAny>> = match kwargs {
            Some(kwargs) => kwargs.get_item(field.name)?,
            None => None,
        };
        let positional: Option<Bound<'_, PyAny>> = if index < args.len() {
            Some(args.get_item(index)?)
        } else {
            None
        };
        let value: Bound<'_, PyAny> = match (positional, keyword) {
            (Some(_), Some(_)) => {
                return Err(PyTypeError::new_err(format!(
                    "{name}.__init__() got multiple values for argument '{}'",
                    field.name
                )));
            }
            (Some(value), None) | (None, Some(value)) => value,
            (None, None) => default_value(py, name, field.name, field.default)?,
        };
        values.push(value.unbind());
    }
    match RECORD_FINISHERS
        .iter()
        .flat_map(|group| group.iter())
        .find(|(record, _)| *record == name)
    {
        Some((_, finish)) => finish(py, values),
        None => Ok(values),
    }
}

fn default_value<'py>(
    py: Python<'py>,
    record: &str,
    field: &str,
    default: FieldDefault,
) -> PyResult<Bound<'py, PyAny>> {
    match default {
        FieldDefault::Required => Err(PyTypeError::new_err(format!(
            "{record}.__init__() missing 1 required positional argument: '{field}'"
        ))),
        FieldDefault::None => Ok(py.None().into_bound(py)),
        FieldDefault::False => Ok(PyBool::new(py, false).to_owned().into_any()),
        FieldDefault::True => Ok(PyBool::new(py, true).to_owned().into_any()),
        FieldDefault::Int(value) => value.into_bound_py_any(py),
        FieldDefault::Text(value) => Ok(PyString::new(py, value).into_any()),
        FieldDefault::TextTuple(texts) => Ok(PyTuple::new(py, texts)?.into_any()),
        FieldDefault::TextFrozenset(texts) => Ok(PyFrozenSet::new(py, texts)?.into_any()),
        FieldDefault::EmptyTuple => Ok(PyTuple::empty(py).into_any()),
        FieldDefault::EmptyDict => Ok(PyDict::new(py).into_any()),
        FieldDefault::EmptyFrozenset => Ok(PyFrozenSet::empty(py)?.into_any()),
        FieldDefault::Member(module, class, member) => imported(py, module, class)?.getattr(member),
        FieldDefault::Call(module, name) => imported(py, module, name)?.call0(),
        FieldDefault::CallText(module, name, text) => imported(py, module, name)?.call1((text,)),
    }
}

/// The values of the fields that take part in equality, hashing and repr.
pub(crate) fn compared_values<'py>(
    record: &Bound<'py, NativeRecord>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = record.py();
    let spec: &RecordSpec = record_spec(&record.get_type())?;
    let values = spec
        .fields
        .iter()
        .zip(record.get().values.iter())
        .filter(|(field, _)| field.compared)
        .map(|(_, value)| value.clone_ref(py))
        .collect::<Vec<Py<PyAny>>>();
    PyTuple::new(py, values)
}

/// `Name(field=value!r, ...)` over the compared fields, as a dataclass repr reads.
pub(crate) fn repr_text(record: &Bound<'_, NativeRecord>) -> PyResult<String> {
    let py: Python<'_> = record.py();
    let cls: Bound<'_, PyType> = record.get_type();
    let spec: &RecordSpec = record_spec(&cls)?;
    let mut parts: Vec<String> = Vec::with_capacity(spec.fields.len());
    for (field, value) in spec.fields.iter().zip(record.get().values.iter()) {
        if field.compared {
            parts.push(format!("{}={}", field.name, value.bind(py).repr()?));
        }
    }
    Ok(format!("{}({})", cls.qualname()?, parts.join(", ")))
}

/// The `dataclasses.FrozenInstanceError` raised when assigning to a record field.
pub(crate) fn frozen_error(py: Python<'_>, name: &str) -> PyErr {
    let message: String = format!("cannot assign to field '{name}'");
    match imported(py, FROZEN_INSTANCE_ERROR.0, FROZEN_INSTANCE_ERROR.1)
        .and_then(|error| error.call1((message.as_str(),)))
    {
        Ok(error) => PyErr::from_value(error),
        Err(_) => PyAttributeError::new_err(message),
    }
}

/// `slf <op> other` over the compared fields, as an `order=True` dataclass compares.
pub(crate) fn ordered_comparison(
    slf: &Bound<'_, NativeRecord>,
    other: &Bound<'_, PyAny>,
    op: CompareOp,
) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = slf.py();
    let name: &str = record_spec(&slf.get_type())?.name;
    let ordered: bool = ORDERED_RECORDS.iter().any(|group| group.contains(&name));
    if !ordered || !other.get_type().is(slf.get_type()) {
        return Ok(py.NotImplemented());
    }
    let other: &Bound<'_, NativeRecord> = other.cast::<NativeRecord>()?;
    compared_values(slf)?
        .as_any()
        .rich_compare(compared_values(other)?, op)?
        .into_py_any(py)
}
