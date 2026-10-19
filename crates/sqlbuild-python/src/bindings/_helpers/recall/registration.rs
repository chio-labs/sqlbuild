//! Register the native Recall classes.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

use crate::bindings::_helpers::recall::sinks::RecallLifecycleSink;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<RecallLifecycleSink>()
}
