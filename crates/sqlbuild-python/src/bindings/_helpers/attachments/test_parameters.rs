//! SQL test `@param("name")` reference scanning for the preview compile attachments.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::test_parameters::main::parameter_references::parameter_references;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(start, end, name)` code-point spans of every reference, or `None` where Python must scan.
#[pyfunction]
fn scan_test_parameter_references(
    sql: &str,
    declared: Vec<String>,
) -> PyResult<Option<Vec<(usize, usize, String)>>> {
    compiler_guard(|| {
        let Some(references) = parameter_references(sql, &declared) else {
            return Ok(None);
        };
        let mut spans: Vec<(usize, usize, String)> = Vec::with_capacity(references.len());
        for reference in references {
            spans.push((reference.start, reference.end, reference.name));
        }
        Ok(Some(spans))
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scan_test_parameter_references, module)?)?;
    Ok(())
}
