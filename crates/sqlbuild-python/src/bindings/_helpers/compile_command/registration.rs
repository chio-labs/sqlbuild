//! Register the `sqb compile` report, artifact writing and reuse recording.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_command::{
    prepared_artifacts, report, reuse_recording, target_writer,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    report::register(module)?;
    reuse_recording::register(module)?;
    target_writer::register(module)?;
    prepared_artifacts::register(module)
}
