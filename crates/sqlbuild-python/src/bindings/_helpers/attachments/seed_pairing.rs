//! Seed declaration pairing for the preview compile attachments.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::seeds::main::pair_seed_declarations::pair_seed_declarations;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// Pair declarations with seed file stems: `(file indices, None)` or `(None, missing index)`.
#[pyfunction]
fn pair_seed_files(
    declarations: Vec<String>,
    stems: Vec<String>,
) -> PyResult<(Option<Vec<usize>>, Option<usize>)> {
    compiler_guard(|| {
        Ok(match pair_seed_declarations(&declarations, &stems) {
            Ok(pairs) => (Some(pairs), None),
            Err(missing) => (None, Some(missing)),
        })
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(pair_seed_files, module)?)?;
    Ok(())
}
