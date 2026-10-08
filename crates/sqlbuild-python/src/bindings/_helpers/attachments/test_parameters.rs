//! SQL test `@param("name")` reference scanning for the preview compile attachments.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::test_parameters::main::parameter_references::parameter_references;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(start, end, name)` by code points.
type Span = (usize, usize, String);

/// The references Python renders and the error it then raises for `owner`, the test case.
#[pyfunction]
fn scan_test_parameter_references(
    sql: &str,
    declared: Vec<String>,
    owner: &str,
) -> PyResult<(Vec<Span>, Option<String>)> {
    compiler_guard(|| {
        let scan = parameter_references(sql, &declared, owner);
        let mut spans: Vec<Span> = Vec::with_capacity(scan.references.len());
        for reference in scan.references {
            spans.push((reference.start, reference.end, reference.name));
        }
        Ok((spans, scan.error))
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scan_test_parameter_references, module)?)?;
    Ok(())
}
