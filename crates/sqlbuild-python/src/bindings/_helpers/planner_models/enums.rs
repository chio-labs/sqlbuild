//! Creates the planner `StrEnum` classes in the native module.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::planner_models::constants::PLANNER_STR_ENUMS;
use pyo3::prelude::{Bound, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyList};

pub(crate) fn register_enums(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let str_enum = imported(py, "enum", "StrEnum")?;
    for (name, members) in PLANNER_STR_ENUMS {
        let options = PyDict::new(py);
        options.set_item("module", "sqlbuild._native")?;
        options.set_item("qualname", *name)?;
        let class = str_enum.call((*name, PyList::new(py, members.iter())?), Some(&options))?;
        module.add(*name, class)?;
    }
    Ok(())
}
