//! Python string constants that name a renamed model or column, for `sqb rename` and `sqb mv`.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_pysource::string_literals::main::string_literal_locations::string_literal_locations;
use sqlbuild_pysource::string_literals::models::StringQuery;

/// The 1-based `(line, column)` of each flagged string constant; none when `contents` does not parse.
#[pyfunction]
#[pyo3(signature = (contents, names, context))]
fn python_string_locations(
    py: Python<'_>,
    contents: &str,
    names: Vec<String>,
    context: Option<&str>,
) -> Vec<(usize, usize)> {
    let version = py.version_info();
    string_literal_locations(
        contents,
        &StringQuery {
            names: &names,
            context,
        },
        (version.major, version.minor),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(python_string_locations, module)?)?;
    Ok(())
}
