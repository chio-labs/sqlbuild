//! Register the native `sqb` argument parsing and command dispatch.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cli::{argv, entry, progress, progress_reporters, progress_text};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    argv::register(module)?;
    entry::register(module)?;
    progress::register(module)?;
    progress_reporters::register(module)?;
    progress_text::register(module)?;
    Ok(())
}
