//! Register the native record base, its field descriptor and every record class.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};

use crate::bindings::_helpers::records::constants::{NATIVE_MODULE, RECORD_SPEC_ATTRIBUTE};
use crate::bindings::_helpers::records::fields::all_specs;
use crate::bindings::_helpers::records::models::{NativeRecord, RecordAttribute, RecordSpec};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py: Python<'_> = module.py();
    module.add_class::<NativeRecord>()?;
    module.add_class::<RecordAttribute>()?;
    let base: Bound<'_, PyAny> = py.get_type::<NativeRecord>().into_any();
    let metaclass: Bound<'_, PyAny> = base.get_type().into_any();
    for (index, spec) in all_specs().enumerate() {
        module.add(spec.name, record_class(&metaclass, &base, (index, spec))?)?;
    }
    Ok(())
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
