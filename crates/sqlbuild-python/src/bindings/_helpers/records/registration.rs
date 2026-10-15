//! Register the native record base, its field descriptor and every record class.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

use crate::bindings::_helpers::records::constants::{
    DATACLASS_FIELD_KIND, DATACLASS_FIELDS_ATTRIBUTE, DATACLASSES_MODULE, NATIVE_MODULE,
    RECORD_SPEC_ATTRIBUTE,
};
use crate::bindings::_helpers::records::fields::all_specs;
use crate::bindings::_helpers::records::models::{NativeRecord, RecordAttribute, RecordSpec};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py: Python<'_> = module.py();
    module.add_class::<NativeRecord>()?;
    module.add_class::<RecordAttribute>()?;
    let base: Bound<'_, PyAny> = py.get_type::<NativeRecord>().into_any();
    let metaclass: Bound<'_, PyAny> = base.get_type().into_any();
    let dataclasses: Bound<'_, PyModule> = py.import(DATACLASSES_MODULE)?;
    for (index, spec) in all_specs().enumerate() {
        let class: Bound<'_, PyAny> = record_class(&metaclass, &base, (index, spec))?;
        class.setattr(
            DATACLASS_FIELDS_ATTRIBUTE,
            dataclass_fields(&dataclasses, spec)?,
        )?;
        module.add(spec.name, class)?;
    }
    Ok(())
}

/// The `dataclasses.Field` table that lets `dataclasses.replace` and `fields` read a record.
fn dataclass_fields<'py>(
    dataclasses: &Bound<'py, PyModule>,
    spec: &RecordSpec,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = dataclasses.py();
    let field_kind: Bound<'py, PyAny> = dataclasses.getattr(DATACLASS_FIELD_KIND)?;
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    for field in spec.fields {
        let options: Bound<'py, PyDict> = PyDict::new(py);
        options.set_item("compare", field.compared)?;
        options.set_item("repr", field.compared)?;
        let declared: Bound<'py, PyAny> = dataclasses.getattr("field")?.call((), Some(&options))?;
        declared.setattr("name", field.name)?;
        declared.setattr("type", "object")?;
        declared.setattr("_field_type", &field_kind)?;
        fields.set_item(field.name, declared)?;
    }
    Ok(fields)
}

/// A `NativeRecord` subclass laid out as `spec`.
fn record_class<'py>(
    metaclass: &Bound<'py, PyAny>,
    base: &Bound<'py, PyAny>,
    (index, spec): (usize, &'static RecordSpec),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = base.py();
    let namespace: Bound<'py, PyDict> = PyDict::new(py);
    namespace.set_item("__module__", NATIVE_MODULE)?;
    namespace.set_item("__qualname__", spec.name)?;
    namespace.set_item("__doc__", spec.doc)?;
    namespace.set_item("__slots__", PyTuple::empty(py))?;
    namespace.set_item(RECORD_SPEC_ATTRIBUTE, index)?;
    let names: Vec<Bound<'py, PyString>> = spec
        .fields
        .iter()
        .map(|field| PyString::new(py, field.name))
        .collect();
    namespace.set_item("__match_args__", PyTuple::new(py, &names)?)?;
    for (position, field) in spec.fields.iter().enumerate() {
        let attribute: Py<RecordAttribute> = Py::new(
            py,
            RecordAttribute {
                index: position,
                name: field.name,
            },
        )?;
        namespace.set_item(field.name, attribute)?;
    }
    metaclass.call1((spec.name, (base,), namespace))
}
