//! Deferred target schema and database templates split natively around known variables.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_model_config::templates::main::deferred_target_segments::deferred_target_segments as segments;
use sqlbuild_model_config::templates::models::DeferredSegment;

/// `(is_variable, text)` pieces of a deferred target field after context substitution.
#[pyfunction]
fn deferred_target_segments(
    template: &str,
    logical: &str,
    context_keys: Vec<String>,
    variables: Vec<String>,
) -> Vec<(bool, String)> {
    segments(template, logical, &context_keys, &variables)
        .into_iter()
        .map(|segment| match segment {
            DeferredSegment::Text(text) => (false, text),
            DeferredSegment::Variable(name) => (true, name),
        })
        .collect()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(deferred_target_segments, module)?)
}
