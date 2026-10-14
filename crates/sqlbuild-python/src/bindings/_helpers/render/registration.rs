//! Register the macro call and macro argument functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::render::{
    authored_sql, declaration_indexes, declaration_values, macro_arguments, macro_calls,
    macro_expansion, macro_expansion_result, macro_modules,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    authored_sql::register(module)?;
    declaration_values::register(module)?;
    declaration_indexes::register(module)?;
    macro_arguments::register(module)?;
    macro_calls::register(module)?;
    macro_expansion::register(module)?;
    macro_expansion_result::register(module)?;
    macro_modules::register(module)?;
    Ok(())
}
