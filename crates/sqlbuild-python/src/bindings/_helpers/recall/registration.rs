//! Register the native Recall classes.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

use crate::bindings::_helpers::discovery::imported_providers::install_recall_writer;
use crate::bindings::_helpers::recall::sinks::RecallLifecycleSink;
use crate::bindings::_helpers::recall::writer::RecallWriter;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<RecallLifecycleSink>()?;
    install_recall_writer(&module.py().get_type::<RecallWriter>());
    module.add_class::<RecallWriter>()
}
