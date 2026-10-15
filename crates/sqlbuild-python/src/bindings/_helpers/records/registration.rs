//! Register the native record base, its field descriptor and every record class.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

use crate::bindings::_helpers::records::constants::{
    DATACLASS_FIELD_KIND, DATACLASS_FIELDS_ATTRIBUTE, DATACLASSES_MODULE, ENUM_MODULE, ENUMS,
    NATIVE_MODULE, RECORD_SPEC_ATTRIBUTE, STR_ENUM,
};
use crate::bindings::_helpers::records::fields::all_specs;
use crate::bindings::_helpers::records::models::{
    EnumSpec, NativeRecord, RecordAttribute, RecordSpec,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py: Python<'_> = module.py();
    module.add_class::<NativeRecord>()?;
    module.add_class::<RecordAttribute>()?;
    let base: Bound<'_, PyAny> = py.get_type::<NativeRecord>().into_any();
    let metaclass: Bound<'_, PyAny> = base.get_type().into_any();
    let str_enum: Bound<'_, PyAny> = py.import(ENUM_MODULE)?.getattr(STR_ENUM)?;
    for spec in ENUMS.iter().flat_map(|group| group.iter()) {
        module.add(spec.name, string_enum(&str_enum, spec)?)?;
    }
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

/// `StrEnum(name, members)` living in `sqlbuild._native`.
fn string_enum<'py>(str_enum: &Bound<'py, PyAny>, spec: &EnumSpec) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = str_enum.py();
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("module", NATIVE_MODULE)?;
    options.set_item("qualname", spec.name)?;
    let members: Vec<(&str, &str)> = spec.members.to_vec();
    let enum_class: Bound<'py, PyAny> = str_enum.call((spec.name, members), Some(&options))?;
    if !spec.doc.is_empty() {
        enum_class.setattr("__doc__", spec.doc)?;
    }
    Ok(enum_class)
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
