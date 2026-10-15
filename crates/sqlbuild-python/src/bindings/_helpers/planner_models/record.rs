//! Frozen value records with dataclass construction, equality, hashing and repr.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use pyo3::IntoPyObject;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple, PyTupleMethods};

/// How a record field is filled when the caller leaves it out.
pub(crate) enum FieldDefault {
    /// The caller must pass the field.
    Required,
    /// `None`.
    NoneValue,
    /// A boolean.
    Bool(bool),
    /// A string.
    Text(&'static str),
    /// A new empty tuple.
    EmptyTuple,
    /// A new empty frozenset.
    EmptyFrozenSet,
    /// A new empty dict.
    EmptyDict,
    /// An enum member, by class and member name.
    Member((&'static str, &'static str), &'static str),
    /// A new instance of a class called without arguments.
    Class((&'static str, &'static str)),
    /// A value built by a function.
    Factory(for<'py> fn(Python<'py>) -> PyResult<Bound<'py, PyAny>>),
}

/// One record field.
pub(crate) struct FieldSpec {
    pub(crate) name: &'static str,
    pub(crate) default: FieldDefault,
    pub(crate) compare: bool,
    pub(crate) repr: bool,
}

/// The fields of one record class.
pub(crate) struct RecordSpec {
    pub(crate) name: &'static str,
    pub(crate) kw_only: bool,
    pub(crate) fields: &'static [FieldSpec],
}

fn default_value<'py>(py: Python<'py>, default: &FieldDefault) -> PyResult<Bound<'py, PyAny>> {
    match default {
        FieldDefault::Required => Ok(py.None().into_bound(py)),
        FieldDefault::NoneValue => Ok(py.None().into_bound(py)),
        FieldDefault::Bool(value) => Ok(value.into_pyobject(py)?.to_owned().into_any()),
        FieldDefault::Text(value) => Ok(PyString::new(py, value).into_any()),
        FieldDefault::EmptyTuple => Ok(PyTuple::empty(py).into_any()),
        FieldDefault::EmptyFrozenSet => Ok(PyFrozenSet::empty(py)?.into_any()),
        FieldDefault::EmptyDict => Ok(PyDict::new(py).into_any()),
        FieldDefault::Member((module, class), member) => {
            imported(py, module, class)?.getattr(*member)
        }
        FieldDefault::Class((module, class)) => imported(py, module, class)?.call0(),
        FieldDefault::Factory(build) => build(py),
    }
}

/// Bind constructor arguments to the record's fields in order, as a dataclass `__init__` does.
pub(crate) fn bind_fields(
    spec: &RecordSpec,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Vec<Py<PyAny>>> {
    let py = args.py();
    if args.len() > 0 && spec.kw_only {
        return Err(PyTypeError::new_err(format!(
            "{}.__init__() takes 1 positional argument but {} were given",
            spec.name,
            args.len() + 1
        )));
    }
    if args.len() > spec.fields.len() {
        return Err(PyTypeError::new_err(format!(
            "{}.__init__() takes {} positional arguments but {} were given",
            spec.name,
            spec.fields.len() + 1,
            args.len() + 1
        )));
    }
    let mut values: Vec<Option<Bound<'_, PyAny>>> = args.iter().map(Some).collect();
    values.resize_with(spec.fields.len(), || None);
    if let Some(kwargs) = kwargs {
        for (key, value) in kwargs.iter() {
            let key: String = key.extract()?;
            let Some(index) = spec.fields.iter().position(|field| field.name == key) else {
                return Err(PyTypeError::new_err(format!(
                    "{}.__init__() got an unexpected keyword argument '{key}'",
                    spec.name
                )));
            };
            if values[index].is_some() {
                return Err(PyTypeError::new_err(format!(
                    "{}.__init__() got multiple values for argument '{key}'",
                    spec.name
                )));
            }
            values[index] = Some(value);
        }
    }
    spec.fields
        .iter()
        .zip(values)
        .map(|(field, value)| match value {
            Some(value) => Ok(value.unbind()),
            None if matches!(field.default, FieldDefault::Required) => {
                Err(PyTypeError::new_err(format!(
                    "{}.__init__() missing 1 required argument: '{}'",
                    spec.name, field.name
                )))
            }
            None => Ok(default_value(py, &field.default)?.unbind()),
        })
        .collect()
}

/// The current field values with `changes` applied, as `dataclasses.replace` binds them.
pub(crate) fn replaced_fields(
    spec: &RecordSpec,
    current: Vec<Bound<'_, PyAny>>,
    changes: Option<&Bound<'_, PyDict>>,
) -> PyResult<Vec<Py<PyAny>>> {
    let mut values: Vec<Py<PyAny>> = current.into_iter().map(Bound::unbind).collect();
    let Some(changes) = changes else {
        return Ok(values);
    };
    for (key, value) in changes.iter() {
        let key: String = key.extract()?;
        let Some(index) = spec.fields.iter().position(|field| field.name == key) else {
            return Err(PyTypeError::new_err(format!(
                "{}.__init__() got an unexpected keyword argument '{key}'",
                spec.name
            )));
        };
        values[index] = value.unbind();
    }
    Ok(values)
}

fn compared<'py>(
    py: Python<'py>,
    spec: &RecordSpec,
    values: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyTuple>> {
    let kept: Vec<Bound<'py, PyAny>> = spec
        .fields
        .iter()
        .zip(values)
        .filter(|(field, _)| field.compare)
        .map(|(_, value)| value.clone())
        .collect();
    PyTuple::new(py, kept)
}

/// Dataclass equality: same class and equal compared fields.
pub(crate) fn record_eq<'py>(
    spec: &RecordSpec,
    (left, right): (&[Bound<'py, PyAny>], Option<&[Bound<'py, PyAny>]>),
    py: Python<'py>,
) -> PyResult<Py<PyAny>> {
    let Some(right) = right else {
        return Ok(py.NotImplemented());
    };
    let equal: bool = compared(py, spec, left)?.eq(compared(py, spec, right)?)?;
    Ok(equal.into_pyobject(py)?.to_owned().into_any().unbind())
}

/// Dataclass hash: the hash of the compared fields.
pub(crate) fn record_hash<'py>(
    spec: &RecordSpec,
    values: &[Bound<'py, PyAny>],
    py: Python<'py>,
) -> PyResult<isize> {
    compared(py, spec, values)?.hash()
}

/// Dataclass repr: `Name(field=value, ...)` over the represented fields.
pub(crate) fn record_repr(spec: &RecordSpec, values: &[Bound<'_, PyAny>]) -> PyResult<String> {
    let mut parts: Vec<String> = Vec::new();
    for (field, value) in spec.fields.iter().zip(values) {
        if field.repr {
            parts.push(format!("{}={}", field.name, value.repr()?));
        }
    }
    Ok(format!("{}({})", spec.name, parts.join(", ")))
}

/// Give a record class the dataclass field table `dataclasses.replace`, `fields` and `asdict` read.
pub(crate) fn install_dataclass_fields(
    class: &Bound<'_, PyAny>,
    spec: &RecordSpec,
) -> PyResult<()> {
    let py = class.py();
    let dataclasses = py.import("dataclasses")?;
    let field_kind = dataclasses.getattr("_FIELD")?;
    let table = PyDict::new(py);
    for field in spec.fields {
        let options = PyDict::new(py);
        options.set_item("compare", field.compare)?;
        options.set_item("repr", field.repr)?;
        let described = dataclasses.call_method("field", (), Some(&options))?;
        described.setattr("name", field.name)?;
        described.setattr("type", "object")?;
        described.setattr("_field_type", &field_kind)?;
        table.set_item(field.name, described)?;
    }
    class.setattr("__dataclass_fields__", table)
}
