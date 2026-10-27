//! The text layout `sqb query` and `sqb recall query` share: a box when the result fits the output width, records otherwise.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use sqlbuild_core::query_command::main::render_query_text::render_query_text;
use sqlbuild_core::query_command::models::{QueryDisplay, QueryLayout};

use crate::bindings::_helpers::boundary::python_calls::imported;

/// The format that always prints one record per row.
pub(crate) const LONG_FORMAT: &str = "long";
/// The width a box may take when stdout is not a terminal.
const PIPED_WIDTH: usize = 120;

/// The terminal's width when stdout is one, else [`PIPED_WIDTH`].
fn output_width(py: Python<'_>) -> PyResult<usize> {
    let stdout: Bound<'_, PyAny> = imported(py, "sys", "stdout")?;
    let interactive: bool = stdout
        .call_method0("isatty")
        .and_then(|answer| answer.is_truthy())
        .unwrap_or(false);
    if !interactive {
        return Ok(PIPED_WIDTH);
    }
    let size: Bound<'_, PyAny> = imported(py, "shutil", "get_terminal_size")?.call0()?;
    size.getattr("columns")?.extract()
}

/// `display` as text: records for `--format long`, otherwise a box when it fits the output.
pub(crate) fn render_text(
    py: Python<'_>,
    display: &QueryDisplay,
    format: Option<&str>,
) -> PyResult<String> {
    let layout: QueryLayout = if format == Some(LONG_FORMAT) {
        QueryLayout::Long
    } else {
        QueryLayout::Fitted {
            width: output_width(py)?,
        }
    };
    Ok(render_query_text(display, layout))
}
