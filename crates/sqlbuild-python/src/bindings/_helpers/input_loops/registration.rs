use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compiled_project::attachment_inputs;
use crate::bindings::_helpers::input_loops::resource_attachment::RESOURCE_ATTACHMENT;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    attachment_inputs::install(RESOURCE_ATTACHMENT);
    crate::bindings::_helpers::input_loops::model_loop::register(module)?;
    crate::bindings::_helpers::input_loops::attachment::register(module)?;
    crate::bindings::_helpers::input_loops::expanded_offsets::register(module)
}
