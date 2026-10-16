//! Execute dbt through the subprocess boundary and finalize results in artifact order.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::dbt_interop::runtime_results::{append_missing, result_ids};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyInt, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use std::collections::HashSet;
use std::time::Instant;

const OPTIONS: (&[&str], &[&str]) = (
    &[
        "runner",
        "options",
        "merged_argv",
        "progress_stream",
        "stdout_stream",
        "use_color",
    ],
    &[
        "skip_message",
        "expected_nodes",
        "on_node_result",
        "on_progress",
    ],
);

fn write(stream: &Bound<'_, PyAny>, text: &str) -> PyResult<()> {
    stream.call_method1("write", (text,))?;
    stream.call_method0("flush")?;
    Ok(())
}

fn expected_total<'py>(
    arguments: &KeywordArguments<'py>,
    argv: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = argv.py();
    let ls = call_with(
        &registry::native(py, NativeAttr::DbtExecutionLsArgv)?,
        &[("argv", argv.clone())],
    )?;
    if ls.is_none() {
        return Ok(py.None().into_bound(py));
    }
    let status = call_with(
        &registry::native(py, NativeAttr::TransientStatusReporter)?,
        &[
            ("stream", arguments.value("progress_stream")?),
            ("use_color", arguments.value("use_color")?),
        ],
    )?;
    status.call_method1("start", ("Resolving dbt execution selection...",))?;
    let start = Instant::now();
    let result = call_with(
        &arguments.value("runner")?.getattr("invoke")?,
        &[
            (
                "argv",
                py.import("builtins")?.getattr("tuple")?.call1((ls,))?,
            ),
            ("cwd", arguments.value("options")?.getattr("project_dir")?),
        ],
    );
    call_with(
        &status.getattr("complete")?,
        &[(
            "message",
            PyString::new(
                py,
                &format!(
                    "Resolved dbt execution selection. ({:.2}s)",
                    start.elapsed().as_secs_f64()
                ),
            )
            .into_any(),
        )],
    )?;
    let result = result?;
    if result.getattr("returncode")?.extract::<i64>()? != 0 {
        return Ok(py.None().into_bound(py));
    }
    let nodes = call_with(
        &registry::native(py, NativeAttr::ParseDbtLsJsonLines)?,
        &[("stdout", result.getattr("stdout")?)],
    )?;
    Ok(PyInt::new(py, nodes.len()?).into_any())
}

fn progress(arguments: &KeywordArguments<'_>, message: &str) -> PyResult<()> {
    let callback = arguments.value("on_progress")?;
    if !callback.is_none() {
        callback.call1((message,))?;
    }
    Ok(())
}

/// Execute selected dbt work and backfill results absent from its JSON event stream.
#[pyfunction]
#[pyo3(signature = (**options))]
fn execute_dbt_commands<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments = KeywordArguments::read(py, "execute_dbt_commands", options, OPTIONS)?;
    let argv = arguments.value("merged_argv")?;
    let output = arguments.value("progress_stream")?;
    let style = call_with(
        &registry::native(py, NativeAttr::CliStyle)?,
        &[("use_color", arguments.value("use_color")?)],
    )?;
    let result_type = registry::class(py, RecordId::DbtCommandExecutionResult)?;
    if argv.is_none() {
        let message = arguments.value("skip_message")?;
        let message = if message.is_none() {
            PyString::new(py, "Skipping dbt: no dbt work selected.").into_any()
        } else {
            message
        };
        write(
            &output,
            &format!(
                "{}\n",
                style
                    .call_method1("muted", (message,))?
                    .extract::<String>()?
            ),
        )?;
        return call_with(
            &result_type,
            &[("returncode", PyInt::new(py, 0).into_any())],
        );
    }
    let name: String = py
        .import("pathlib")?
        .getattr("Path")?
        .call1((argv.get_item(0)?,))?
        .getattr("name")?
        .extract()?;
    let detail = if argv.len()? >= super::constants::COMMAND_AND_SUBCOMMAND_ARGUMENT_COUNT {
        format!("{name} {}", argv.get_item(1)?.extract::<String>()?)
    } else {
        name
    };
    write(
        &output,
        &format!(
            "{}  {}\n\n",
            style
                .call_method1("dbt_execution_label", ("dbt execution",))?
                .extract::<String>()?,
            style
                .call_method1("muted", (detail,))?
                .extract::<String>()?
        ),
    )?;
    let expected_nodes = arguments.value("expected_nodes")?;
    let expected: Option<HashSet<String>> = if expected_nodes.is_none() {
        None
    } else {
        Some(result_ids(&expected_nodes)?)
    };
    let total = if let Some(ids) = &expected {
        PyInt::new(py, ids.len()).into_any()
    } else {
        expected_total(&arguments, &argv)?
    };
    let dbt_options = arguments.value("options")?;
    let mut target = dbt_options.getattr("target_path")?;
    let project_dir = dbt_options.getattr("project_dir")?;
    if target.is_none() && !project_dir.is_none() {
        target = project_dir.call_method1("__truediv__", ("target",))?;
    }
    let (returncode, streamed): (Bound<'py, PyAny>, Bound<'py, PyAny>) = call_with(
        &registry::native(py, NativeAttr::ExecuteDbtJsonEventStream)?,
        &[
            ("argv", argv),
            ("cwd", project_dir),
            ("stream", arguments.value("stdout_stream")?),
            ("use_color", arguments.value("use_color")?),
            ("target_path", target.clone()),
            ("display_total", total.clone()),
            ("on_node_result", arguments.value("on_node_result")?),
        ],
    )?
    .extract()?;
    progress(&arguments, "Finalizing dbt run...")?;
    let streamed_ids = result_ids(&streamed)?;
    let mut filtered: Vec<Bound<'py, PyAny>> = Vec::new();
    for result in streamed.try_iter()? {
        let result = result?;
        let id: String = result.getattr("unique_id")?.extract()?;
        if expected.as_ref().is_none_or(|ids| ids.contains(&id)) {
            filtered.push(result);
        }
    }
    let results = append_missing(
        &PyTuple::new(py, filtered)?.into_any(),
        &target,
        expected.as_ref(),
    )?;
    let mut appended: Vec<Bound<'py, PyAny>> = Vec::new();
    for result in results.try_iter()? {
        let result = result?;
        if !streamed_ids.contains(&result.getattr("unique_id")?.extract::<String>()?) {
            appended.push(result);
        }
    }
    let count = results.len()? - appended.len();
    for (offset, result) in appended.into_iter().enumerate() {
        let rendered = call_with(
            &registry::native(py, NativeAttr::RenderDbtNodeResult)?,
            &[
                ("result", result.clone()),
                ("use_color", style.getattr("use_color")?),
                (
                    "display_index",
                    PyInt::new(py, count + offset + 1).into_any(),
                ),
                (
                    "display_total",
                    if total.is_none() {
                        PyInt::new(py, results.len()?).into_any()
                    } else {
                        total.clone()
                    },
                ),
            ],
        )?;
        write(
            &arguments.value("stdout_stream")?,
            &rendered.extract::<String>()?,
        )?;
        let callback = arguments.value("on_node_result")?;
        if !callback.is_none() {
            callback.call1((result,))?;
        }
    }
    progress(&arguments, "Finalized dbt run.")?;
    call_with(
        &result_type,
        &[("returncode", returncode), ("node_results", results)],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(execute_dbt_commands, module)?)
}
