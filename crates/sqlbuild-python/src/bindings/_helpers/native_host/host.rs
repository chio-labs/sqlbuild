//! Resolve host entries: targets read once from `sqlbuild._native_host`, attributes read live.

use pyo3::exceptions::PyImportError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple, PyTupleMethods};

use crate::bindings::_helpers::native_host::constants::{
    HOST_ENTRIES, HOST_MODULE, HOST_TARGETS_FUNCTION,
};
use crate::bindings::_helpers::native_host::models::HostId;

/// One entry's target module path and attribute name.
type Target = (Py<PyString>, Py<PyString>);

/// Every entry's target, grouped and ordered as `HOST_ENTRIES`.
static TARGETS: PyOnceLock<Vec<Vec<Target>>> = PyOnceLock::new();

fn missing(name: &str) -> pyo3::PyErr {
    PyImportError::new_err(format!("{HOST_MODULE} does not define host entry '{name}'"))
}

/// Read every entry's target from the host module, failing on the first entry it lacks.
fn host_targets(py: Python<'_>) -> PyResult<Vec<Vec<Target>>> {
    let declared: Bound<'_, PyDict> = py
        .import(HOST_MODULE)?
        .getattr(HOST_TARGETS_FUNCTION)?
        .call0()?
        .cast_into::<PyDict>()?;
    let mut groups: Vec<Vec<Target>> = Vec::with_capacity(HOST_ENTRIES.len());
    for group in HOST_ENTRIES {
        let mut targets: Vec<Target> = Vec::with_capacity(group.len());
        for entry in group {
            let target: Bound<'_, PyTuple> = declared
                .get_item(entry.name)?
                .ok_or_else(|| missing(entry.name))?
                .cast_into::<PyTuple>()?;
            targets.push((
                target.get_item(0)?.cast_into::<PyString>()?.unbind(),
                target.get_item(1)?.cast_into::<PyString>()?.unbind(),
            ));
        }
        groups.push(targets);
    }
    Ok(groups)
}

/// The host entry `id`: its target module imported and the attribute read on every call.
pub(crate) fn entry<'py>(py: Python<'py>, id: impl Into<HostId>) -> PyResult<Bound<'py, PyAny>> {
    let id: HostId = id.into();
    let targets: &Vec<Vec<Target>> = TARGETS.get_or_try_init(py, || host_targets(py))?;
    let (module, attribute): &Target = &targets[id.edge as usize][id.index];
    py.import(module.bind(py))?.getattr(attribute.bind(py))
}
