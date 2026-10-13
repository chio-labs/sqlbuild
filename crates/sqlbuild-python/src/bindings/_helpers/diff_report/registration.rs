//! `sqb diff` output: the terminal summary, JSON documents, output publication and exit codes.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python, pyfunction,
    wrap_pyfunction,
};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_cli::diff_report::main::diff_exit_code::diff_exit_code;
use sqlbuild_cli::diff_report::main::render_diff_error_json::render_diff_error_json as error_document;
use sqlbuild_cli::diff_report::main::render_diff_json::render_diff_json;
use sqlbuild_cli::diff_report::main::render_diff_text::render_diff_text;
use sqlbuild_cli::diff_report::models::{
    DiffDocumentOptions, DiffErrorFacts, DiffExampleOptions, DiffModelFacts, DiffTextOptions,
};

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, imported};
use crate::bindings::_helpers::diff_report::facts::{diff_facts, json_of};
use crate::bindings::_helpers::frontier::encoder::emit_error;

const DEFAULT_MAX_VALUE_LENGTH: usize = 160;
const COLOR_MODULE: &str = "sqlbuild.presentation.main.supports_color";
const TEXT_OPTIONS: (&[&str], &[&str]) = (
    &[
        "result",
        "from_label",
        "to_label",
        "mode_label",
        "use_color",
        "verbose",
        "max_column_examples",
        "max_row_only_examples",
    ],
    &["max_value_length", "suppress_example_values", "outcome"],
);
const JSON_OPTIONS: (&[&str], &[&str]) = (
    &["result", "from_label", "to_label"],
    &[
        "max_value_length",
        "suppress_example_values",
        "phase_seconds",
        "outcome",
    ],
);
const ERROR_OPTIONS: (&[&str], &[&str]) =
    (&["status", "code", "message"], &["help_text", "size_guard"]);
const WRITE_OPTIONS: (&[&str], &[&str]) = (
    &[
        "request",
        "from_label",
        "to_label",
        "max_column_examples",
        "max_row_only_examples",
        "result",
    ],
    &["phase_seconds", "outcome"],
);
const EXIT_OPTIONS: (&[&str], &[&str]) = (&["result"], &["query_row_comparison"]);

fn optional_string(value: Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    value.extract().map(Some)
}

fn phase_seconds(value: Bound<'_, PyAny>) -> PyResult<Option<Vec<(String, f64)>>> {
    if value.is_none() {
        return Ok(None);
    }
    let mapping: Bound<'_, PyDict> = value.downcast_into()?;
    let mut phases: Vec<(String, f64)> = Vec::new();
    for (phase, seconds) in mapping.iter() {
        phases.push((phase.extract()?, seconds.extract()?));
    }
    Ok(Some(phases))
}

/// The example options of explicit `max_value_length`/`suppress_example_values` arguments.
fn example_options(arguments: &KeywordArguments<'_>) -> PyResult<DiffExampleOptions> {
    Ok(DiffExampleOptions {
        max_value_length: if arguments.passed("max_value_length")? {
            {
                let limit: Bound<'_, PyAny> = arguments.value("max_value_length")?;
                if limit.is_none() {
                    None
                } else {
                    Some(limit.extract()?)
                }
            }
        } else {
            Some(DEFAULT_MAX_VALUE_LENGTH)
        },
        suppress_values: arguments.flag("suppress_example_values")?,
    })
}

fn document_options(
    arguments: &KeywordArguments<'_>,
    examples: DiffExampleOptions,
) -> PyResult<DiffDocumentOptions> {
    Ok(DiffDocumentOptions {
        from_label: arguments.value("from_label")?.extract()?,
        to_label: arguments.value("to_label")?.extract()?,
        examples,
        outcome: optional_string(arguments.value("outcome")?)?,
        phase_seconds: phase_seconds(arguments.value("phase_seconds")?)?,
    })
}

fn json_text(models: &[DiffModelFacts], options: &DiffDocumentOptions) -> PyResult<String> {
    render_diff_json(models, options).map_err(emit_error)
}

/// Render the concise terminal summary of a diff result.
#[pyfunction]
#[pyo3(signature = (**options))]
fn render_diff_output(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<String> {
    let arguments: KeywordArguments<'_> =
        KeywordArguments::read(py, "render_diff_output", options, TEXT_OPTIONS)?;
    let models: Vec<DiffModelFacts> = diff_facts(&arguments.value("result")?)?;
    let document: DiffDocumentOptions = document_options(&arguments, example_options(&arguments)?)?;
    Ok(render_diff_text(
        &models,
        &document,
        &DiffTextOptions {
            mode_label: arguments.value("mode_label")?.extract()?,
            use_color: arguments.flag("use_color")?,
            verbose: arguments.flag("verbose")?,
            max_column_examples: arguments.value("max_column_examples")?.extract()?,
            max_row_only_examples: arguments.value("max_row_only_examples")?.extract()?,
        },
    ))
}

/// Render one stable structured diff document.
#[pyfunction]
#[pyo3(signature = (**options))]
fn render_diff_json_output(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<String> {
    let arguments: KeywordArguments<'_> =
        KeywordArguments::read(py, "render_diff_json_output", options, JSON_OPTIONS)?;
    let models: Vec<DiffModelFacts> = diff_facts(&arguments.value("result")?)?;
    json_text(
        &models,
        &document_options(&arguments, example_options(&arguments)?)?,
    )
}

/// Render a machine-readable incomplete or execution-failure outcome.
#[pyfunction]
#[pyo3(signature = (**options))]
fn render_diff_error_json(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<String> {
    let arguments: KeywordArguments<'_> =
        KeywordArguments::read(py, "render_diff_error_json", options, ERROR_OPTIONS)?;
    let size_guard: Bound<'_, PyAny> = arguments.value("size_guard")?;
    error_document(&DiffErrorFacts {
        status: arguments.value("status")?.extract()?,
        code: arguments.value("code")?.extract()?,
        message: arguments.value("message")?.extract()?,
        help: optional_string(arguments.value("help_text")?)?,
        size_guard: if size_guard.is_none() {
            None
        } else {
            Some(json_of(&size_guard)?)
        },
    })
    .map_err(emit_error)
}

fn mode_label(request: &Bound<'_, PyAny>) -> PyResult<String> {
    if request.getattr("schema_only")?.is_truthy()? {
        return Ok("schema-only".to_owned());
    }
    let bounded: Bound<'_, PyAny> = request.getattr("bounded")?;
    if bounded.is_truthy()? {
        return Ok(format!("bounded {}", bounded.str()?));
    }
    Ok("full".to_owned())
}

fn write_stdout(py: Python<'_>, text: &str) -> PyResult<()> {
    imported(py, "sys", "stdout")?.call_method1("write", (format!("{text}\n"),))?;
    Ok(())
}

/// Write the requested JSON file, then print the JSON document or the terminal summary.
#[pyfunction]
#[pyo3(signature = (**options))]
fn write_diff_output(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<()> {
    let arguments: KeywordArguments<'_> =
        KeywordArguments::read(py, "write_diff_output", options, WRITE_OPTIONS)?;
    let request: Bound<'_, PyAny> = arguments.value("request")?;
    let max_value_length: Bound<'_, PyAny> = request.getattr("max_value_length")?;
    let examples: DiffExampleOptions = DiffExampleOptions {
        max_value_length: if request.getattr("full_example_values")?.is_truthy()? {
            None
        } else if max_value_length.is_truthy()? {
            Some(max_value_length.extract()?)
        } else {
            Some(DEFAULT_MAX_VALUE_LENGTH)
        },
        suppress_values: request.getattr("suppress_example_values")?.is_truthy()?,
    };
    let document: DiffDocumentOptions = document_options(&arguments, examples)?;
    let models: Vec<DiffModelFacts> = diff_facts(&arguments.value("result")?)?;
    let path: Bound<'_, PyAny> = request.getattr("json_output_path")?;
    if !path.is_none() {
        let keywords: Bound<'_, PyDict> = PyDict::new(py);
        keywords.set_item("parents", true)?;
        keywords.set_item("exist_ok", true)?;
        path.getattr("parent")?
            .call_method("mkdir", (), Some(&keywords))?;
        let encoding: Bound<'_, PyDict> = PyDict::new(py);
        encoding.set_item("encoding", "utf-8")?;
        path.call_method(
            "write_text",
            (format!("{}\n", json_text(&models, &document)?),),
            Some(&encoding),
        )?;
    }
    if request.getattr("json_output")?.is_truthy()? {
        return write_stdout(py, &json_text(&models, &document)?);
    }
    let use_color: bool = !request.getattr("no_color")?.is_truthy()?
        && imported(py, COLOR_MODULE, "supports_color")?
            .call0()?
            .is_truthy()?;
    write_stdout(
        py,
        &render_diff_text(
            &models,
            &document,
            &DiffTextOptions {
                mode_label: mode_label(&request)?,
                use_color,
                verbose: request.getattr("verbose")?.is_truthy()?,
                max_column_examples: arguments.value("max_column_examples")?.extract()?,
                max_row_only_examples: arguments.value("max_row_only_examples")?.extract()?,
            },
        ),
    )
}

/// `(outcome, exit_code)` of a finished diff, with query row-comparison semantics on request.
#[pyfunction]
#[pyo3(signature = (**options))]
fn resolve_diff_outcome(
    py: Python<'_>,
    options: Option<Bound<'_, PyDict>>,
) -> PyResult<(String, i32)> {
    let arguments: KeywordArguments<'_> =
        KeywordArguments::read(py, "resolve_diff_outcome", options, EXIT_OPTIONS)?;
    let models: Vec<DiffModelFacts> = diff_facts(&arguments.value("result")?)?;
    Ok(diff_exit_code(
        &models,
        arguments.flag("query_row_comparison")?,
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_diff_output, module)?)?;
    module.add_function(wrap_pyfunction!(render_diff_json_output, module)?)?;
    module.add_function(wrap_pyfunction!(render_diff_error_json, module)?)?;
    module.add_function(wrap_pyfunction!(write_diff_output, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_diff_outcome, module)?)
}
