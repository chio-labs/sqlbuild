//! Register the macro bridge's functions and classes on the extension module.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

use crate::macro_bridge::_helpers::functions::{scan_macro_call_sites, splice_macro_calls};
use crate::macro_bridge::models::MacroCallMemo;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scan_macro_call_sites, module)?)?;
    module.add_function(wrap_pyfunction!(splice_macro_calls, module)?)?;
    module.add_class::<MacroCallMemo>()?;
    Ok(())
}
