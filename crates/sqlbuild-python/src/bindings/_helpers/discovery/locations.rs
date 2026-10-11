//! Authored locations Python consumers read: YAML entry lines and SQL-test helper spans.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::sql_test_attachment::main::sql_test_cte_location::sql_test_cte_location;
use sqlbuild_analysis::sql_test_attachment::models::CteLocation;
use sqlbuild_discovery::yaml_files::main::yaml_entry_lines::yaml_entry_lines;

/// Each outermost `- name:` entry name with its 1-based line.
#[pyfunction]
fn yaml_entry_line_index(contents: &str) -> Vec<(String, usize)> {
    yaml_entry_lines(contents)
}

/// `(line, column, end line, end column)` of a helper problem in one SQL test block.
#[pyfunction]
#[pyo3(signature = (contents, sql_body, cte_name, call))]
fn sql_test_cte_span(
    contents: &str,
    sql_body: &str,
    cte_name: &str,
    call: Option<&str>,
) -> (usize, usize, usize, usize) {
    let location: CteLocation = sql_test_cte_location(contents, sql_body, cte_name, call);
    (
        location.line,
        location.column,
        location.end_line,
        location.end_column,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(yaml_entry_line_index, module)?)?;
    module.add_function(wrap_pyfunction!(sql_test_cte_span, module)?)?;
    Ok(())
}
