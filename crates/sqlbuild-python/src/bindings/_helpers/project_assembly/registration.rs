//! Register the native project assembly functions.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

use crate::bindings::_helpers::project_assembly::models::{
    NativeModelFacts, NativeProjectFacts, NativeProjectResources, NativeResourceFailure,
};
use crate::bindings::_helpers::project_assembly::{
    native_resources, resources, syntax_checks, syntax_validation,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeProjectResources>()?;
    module.add_class::<NativeResourceFailure>()?;
    module.add_class::<NativeModelFacts>()?;
    module.add_class::<NativeProjectFacts>()?;
    native_resources::register(module)?;
    syntax_validation::register(module)?;
    syntax_checks::register(module)?;
    resources::register(module)
}
