//! The first reference call executable SQL still contains.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyString, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::reference_markers::main::unresolved_reference_marker::unresolved_reference_marker;
use sqlbuild_attachments::sql_lexing::main::unclosed_message::unclosed_message;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// The kind index of the first unresolved reference call, or the unclosed-construct message.
#[pyfunction]
fn unresolved_reference_marker_kind(
    sql: &Bound<'_, PyString>,
    context: &str,
) -> PyResult<(Option<usize>, Option<String>)> {
    let text = sql.to_string_lossy();
    compiler_guard(|| {
        Ok(match unresolved_reference_marker(&text) {
            Ok(marker) => (marker, None),
            Err(construct) => (None, Some(unclosed_message(context, construct))),
        })
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(unresolved_reference_marker_kind, module)?)?;
    Ok(())
}
