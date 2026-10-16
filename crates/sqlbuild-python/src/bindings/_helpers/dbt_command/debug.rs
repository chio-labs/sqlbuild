//! `sqb dbt debug`: dbt's own diagnostics, then SQLBuild's.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use sqlbuild_core::dbt_command::constants::NO_CONNECTION_OPTION;

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::dbt_command::auto_init::args_tuple;
use crate::bindings::_helpers::dbt_command::support::{color_enabled, flag, status, stream};
use crate::bindings::_helpers::records::ids::NativeAttr;
use crate::bindings::_helpers::records::registry;

/// Run `body` under a stderr status line that is always closed; returns its exit code.
fn with_status(
    py: Python<'_>,
    (message, use_color): (&str, bool),
    body: impl FnOnce() -> PyResult<i64>,
) -> PyResult<i64> {
    let reporter: Bound<'_, PyAny> = status(&stream(py, "stderr")?, use_color)?;
    reporter.call_method1("start", (message,))?;
    let outcome: PyResult<i64> = body();
    let closed: PyResult<Bound<'_, PyAny>> = reporter.call_method0("close");
    let code: i64 = outcome?;
    closed?;
    Ok(code)
}

/// Run dbt debug, then SQLBuild diagnostics; 0 only when both pass.
pub(crate) fn run_dbt_debug(
    project_dir: &Bound<'_, PyAny>,
    args: &[String],
    no_color: bool,
) -> PyResult<i32> {
    let py: Python<'_> = project_dir.py();
    let use_color: bool = !no_color && color_enabled(py)?;
    let dbt_code: i64 = with_status(py, ("Running dbt debug...", use_color), || {
        call_with(
            &registry::native(py, NativeAttr::DebugDbtFromProject)?,
            &[
                ("project_dir", project_dir.clone()),
                ("args", args_tuple(py, args)?),
                ("stdout_stream", stream(py, "stdout")?),
                ("stderr_stream", stream(py, "stderr")?),
            ],
        )?
        .extract()
    })?;
    stream(py, "stdout")?.call_method1("write", ("\n",))?;
    let sqlbuild_code: i64 =
        with_status(py, ("Running SQLBuild diagnostics...", use_color), || {
            call_with(
                &registry::native(py, NativeAttr::RunDebugCommand)?,
                &[
                    ("project_dir", project_dir.clone()),
                    ("no_color", flag(py, no_color)),
                    (
                        "no_connection",
                        flag(py, args.iter().any(|arg| arg == NO_CONNECTION_OPTION)),
                    ),
                    ("json_output", flag(py, false)),
                ],
            )?
            .extract()
        })?;
    Ok(i32::from(dbt_code != 0 || sqlbuild_code != 0))
}
