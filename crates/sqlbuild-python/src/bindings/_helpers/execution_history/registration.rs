//! Register native execution history storage and entry points.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

use crate::bindings::_helpers::execution_history::functions;
use crate::bindings::_helpers::execution_history::postgres::PostgresExecutionHistory;
use crate::bindings::_helpers::execution_history::sqlite::SqliteExecutionHistory;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SqliteExecutionHistory>()?;
    module.add_class::<PostgresExecutionHistory>()?;
    functions::register(module)
}
