//! `sqb test`: compile the selected SQL unit tests, inspect or run them, and report.

use std::collections::{BTreeSet, HashMap};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyInt, PyString, PyTuple};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, StdlibJsonOptions};
use sqlbuild_core::test_command::main::parameterized_test_label::parameterized_test_label;
use sqlbuild_core::test_command::main::render_test_completion::render_test_completion;
use sqlbuild_core::test_command::main::render_test_inspection::render_test_inspection;
use sqlbuild_core::test_command::main::render_test_ready::render_test_ready;
use sqlbuild_core::test_command::main::test_exit_code::test_exit_code;
use sqlbuild_core::test_command::main::test_group_name::test_group_name;
use sqlbuild_core::test_command::main::test_name_width::test_name_width;
use sqlbuild_core::test_command::main::test_outcome_status::test_outcome_status;
use sqlbuild_core::test_command::models::{
    TestFailure, TestInspectionEntry, TestParameter, TestPlanWarning,
};

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::result_output::integration_values::json_value;

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMMAND_MODELS: &str = "sqlbuild.cli.commands.models";
const INVOCATION_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.command_invocation";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild.cli.commands._helpers.planning.external_refs";
const STATIC_COMMAND_MODULE: &str = "sqlbuild.compiler.pipeline.main.static_command";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const TEST_PLAN_MODULE: &str = "sqlbuild.compiler.planner.main.commands._sql_test";
const PLANNER_ERRORS: &str = "sqlbuild.compiler.planner.exceptions";
const NESTED_PROGRESS_MODULE: &str =
    "sqlbuild.cli.progress.classes.nested_command_progress_callbacks";
const PROGRESS_MODELS: &str = "sqlbuild.cli.progress.models";
const STATUS_REPORTER_MODULE: &str = "sqlbuild.presentation.classes.transient_status_reporter";
const EXECUTOR_PIPELINE_MODELS: &str = "sqlbuild.executor.pipeline.models";
const EXECUTOR_RUN_MODULE: &str = "sqlbuild.executor.pipeline.main.run";
const RESOURCE_ID_MODULE: &str = "sqlbuild.executor.testing.main.resource_id";
const RUNTIME_TARGET_MODULE: &str = "sqlbuild.cli.target_artifacts.main._write_test_runtime_target";
const DECIMAL_KIND: &str = "decimal";
const PASS_OUTCOME: &str = "pass";
const EXPECT_LABEL: &str = "expect";
const UNKNOWN_GROUP: &str = "(unknown)";
const EXECUTION_COMMAND: &str = "sqb test";
const UNKNOWN_CASE_CODE: &str = "S008";

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

fn strings(values: Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    values.try_iter()?.map(|value| value?.extract()).collect()
}

/// A payload as `json.dumps(payload, ensure_ascii=True, separators=(",", ":"))`.
fn compact_json(payload: &Bound<'_, PyAny>) -> PyResult<String> {
    let Some(value) = json_value(payload)? else {
        let options: Bound<'_, PyDict> = PyDict::new(payload.py());
        options.set_item("ensure_ascii", true)?;
        options.set_item("separators", (",", ":"))?;
        return payload
            .py()
            .import("json")?
            .call_method("dumps", (payload,), Some(&options))?
            .extract();
    };
    dumps(
        &value,
        &JsonDialect::Stdlib(StdlibJsonOptions::new(None).with_separators(",", ":")),
    )
    .map_err(|error| PyValueError::new_err(format!("{error:?}")))
}

/// The label of one test or result: its name, plus source and values for parameterized cases.
fn test_label(item: &Bound<'_, PyAny>, name_field: &str) -> PyResult<String> {
    let name: String = item.getattr(name_field)?.extract()?;
    let source_path: Bound<'_, PyAny> = item.getattr("source_path")?;
    let values: Vec<Bound<'_, PyAny>> = item
        .getattr("parameter_values")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    if source_path.is_none() || values.is_empty() {
        return Ok(name);
    }
    let mut schema: HashMap<String, Bound<'_, PyAny>> = HashMap::new();
    for declaration in item.getattr("parameter_schema")?.try_iter()? {
        let declaration: Bound<'_, PyAny> = declaration?;
        schema.insert(declaration.getattr("name")?.extract()?, declaration);
    }
    let mut parameters: Vec<TestParameter> = Vec::new();
    for pair in values {
        let (value_name, value): (String, Bound<'_, PyAny>) = pair.extract()?;
        let declaration: &Bound<'_, PyAny> = schema
            .get(&value_name)
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(value_name.clone()))?;
        let raw: Bound<'_, PyAny> = value.getattr("value")?;
        let kind: String = value.getattr("kind")?.getattr("value")?.extract()?;
        let payload: Bound<'_, PyAny> = if kind == DECIMAL_KIND {
            raw.str()?.into_any()
        } else {
            raw
        };
        parameters.push(TestParameter {
            name: value_name,
            value_type: declaration
                .getattr("value_type")?
                .getattr("value")?
                .extract()?,
            nullable: declaration.getattr("nullable")?.is_truthy()?,
            rendered: compact_json(&payload)?,
        });
    }
    let path: String = source_path.call_method0("as_posix")?.extract()?;
    Ok(parameterized_test_label(&name, Some(&path), &parameters))
}

/// The shared name column width of test rows and their expectation rows.
fn name_width(entries: &Bound<'_, PyAny>) -> PyResult<usize> {
    let mut labels: Vec<String> = Vec::new();
    let mut children: Vec<String> = Vec::new();
    for entry in entries.try_iter()? {
        let entry: Bound<'_, PyAny> = entry?;
        labels.push(test_label(&entry, "name")?);
        for step in entry.getattr("chain")?.try_iter()? {
            let step: Bound<'_, PyAny> = step?;
            if step.getattr("expected_cte_sql")?.is_truthy()? {
                children.push(format!(
                    "expected {}",
                    step.getattr("model_name")?.extract::<String>()?
                ));
            }
        }
        for assertion in entry.getattr("assertions")?.try_iter()? {
            children.push(format!(
                "assertion {}",
                assertion?.getattr("name")?.extract::<String>()?
            ));
        }
    }
    Ok(test_name_width(&labels, &children))
}

fn outcome_status(outcome: &Bound<'_, PyAny>) -> PyResult<&'static str> {
    Ok(test_outcome_status(
        &outcome.getattr("value")?.extract::<String>()?,
    ))
}

/// Nested `expect` rows of a completed test, one per step.
fn expectation_rows<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = result.py();
    let row_class: Bound<'py, PyAny> = imported(py, PROGRESS_MODELS, "NestedProgressChildRow")?;
    let name: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "format_expectation_name")?;
    let detail: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "format_expectation_detail")?;
    let mut rows: Vec<Bound<'py, PyAny>> = Vec::new();
    for step in result.getattr("step_results")?.try_iter()? {
        let step: Bound<'py, PyAny> = step?;
        rows.push(call_with(
            &row_class,
            &[
                ("label", text(py, EXPECT_LABEL)),
                ("name", name.call1((step.getattr("model_name")?,))?),
                (
                    "status_text",
                    text(py, outcome_status(&step.getattr("outcome")?)?),
                ),
                ("detail", detail.call1((&step,))?),
            ],
        )?);
    }
    PyTuple::new(py, rows)
}

/// The model a planned test's progress rows are grouped under.
fn entry_group(entry: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut chain: Vec<(String, bool)> = Vec::new();
    for step in entry.getattr("chain")?.try_iter()? {
        let step: Bound<'_, PyAny> = step?;
        chain.push((
            step.getattr("model_name")?.extract()?,
            !step.getattr("expected_cte_sql")?.is_none(),
        ));
    }
    Ok(test_group_name(&chain))
}

/// Forward test progress, completions and connection timing to their reporters.
#[pyclass(module = "sqlbuild._native", frozen)]
struct TestCallbackRelay {
    progress: Py<PyAny>,
    event_writer: Py<PyAny>,
    plan_output: Py<PyAny>,
    connection: Py<PyAny>,
}

#[pymethods]
impl TestCallbackRelay {
    fn on_test_start(&self, py: Python<'_>, entry: &Bound<'_, PyAny>) -> PyResult<()> {
        call_with(
            &self.progress.bind(py).getattr("on_item_start")?,
            &[
                ("group_name", text(py, &entry_group(entry)?)),
                ("item_name", text(py, &test_label(entry, "name")?)),
                ("canonical_resource_name", entry.getattr("name")?),
            ],
        )?;
        Ok(())
    }

    fn on_test_complete(&self, py: Python<'_>, result: &Bound<'_, PyAny>) -> PyResult<()> {
        let mut group: String = String::new();
        if let Some(step) = result.getattr("step_results")?.try_iter()?.next() {
            group = step?.getattr("model_name")?.extract()?;
        }
        if group.is_empty() {
            group = UNKNOWN_GROUP.to_owned();
        }
        let resource_id: Bound<'_, PyAny> = call_with(
            &imported(py, RESOURCE_ID_MODULE, "sql_test_resource_id")?,
            &[
                ("test_name", result.getattr("test_name")?),
                ("source_path", result.getattr("source_path")?),
                ("block_index", result.getattr("block_index")?),
                ("case_name", result.getattr("case_name")?),
            ],
        )?;
        call_with(
            &self.progress.bind(py).getattr("on_item_complete")?,
            &[
                ("group_name", text(py, &group)),
                ("item_name", text(py, &test_label(result, "test_name")?)),
                (
                    "status_text",
                    text(py, outcome_status(&result.getattr("outcome")?)?),
                ),
                ("child_rows", expectation_rows(result)?.into_any()),
                ("error_code", result.getattr("error_code")?),
                ("error_help", result.getattr("error_help")?),
                ("error_message", result.getattr("error_message")?),
                ("canonical_resource_name", result.getattr("test_name")?),
                ("canonical_resource_id", resource_id),
            ],
        )?;
        call_with(
            &self.event_writer.bind(py).getattr("write_build_result")?,
            &[
                ("result", result.clone()),
                ("plan", self.plan_output.bind(py).clone()),
                ("command", text(py, "test")),
            ],
        )?;
        Ok(())
    }

    fn on_connection_complete(
        &self,
        py: Python<'_>,
        connection_count: i64,
        elapsed_seconds: f64,
    ) -> PyResult<()> {
        self.connection_call(
            py,
            "on_connection_complete",
            (connection_count, elapsed_seconds),
        )
    }

    fn on_connection_error(
        &self,
        py: Python<'_>,
        connection_count: i64,
        elapsed_seconds: f64,
    ) -> PyResult<()> {
        self.connection_call(
            py,
            "on_connection_error",
            (connection_count, elapsed_seconds),
        )
    }
}

impl TestCallbackRelay {
    fn connection_call(
        &self,
        py: Python<'_>,
        method: &str,
        (connection_count, elapsed_seconds): (i64, f64),
    ) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("connection_count", connection_count)?;
        options.set_item("elapsed_seconds", elapsed_seconds)?;
        self.connection
            .bind(py)
            .call_method(method, (), Some(&options))?;
        Ok(())
    }
}

fn unknown_case(py: Python<'_>, message: String) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", UNKNOWN_CASE_CODE)?;
        imported(py, PLANNER_ERRORS, "PlannerInputError")?.call((message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// Compile the selected tests and refuse a `--case` that matched none of them.
fn compile_tests<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let discovered: Bound<'py, PyAny> = invocation.getattr("discovered_inputs")?;
    let adapter: Bound<'py, PyAny> = invocation.getattr("adapter")?;
    let resolver: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            EXTERNAL_REFS_MODULE,
            "resolve_external_sql_reference_resolver",
        )?,
        &[
            ("project_dir", invocation.getattr("effective_project_dir")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let options: Bound<'py, PyAny> = call_with(
        &imported(py, PIPELINE_MODELS, "CompilePipelineOptions")?,
        &[
            ("selected_target", request.getattr("selected_target")?),
            ("no_sql_validation", request.getattr("no_sql_validation")?),
            (
                "source_deferral_enabled",
                PyBool::new(py, false).to_owned().into_any(),
            ),
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            (
                "accepts_unit_test_selectors",
                PyBool::new(py, true).to_owned().into_any(),
            ),
            (
                "connection_config",
                invocation.getattr("connection_config")?,
            ),
            ("cli_vars", request.getattr("cli_vars")?),
            ("external_sql_reference_resolver", resolver),
        ],
    )?;
    let context: Bound<'py, PyAny> = call_with(
        &imported(py, STATIC_COMMAND_MODULE, "compile_static_command_context")?,
        &[
            ("discovered_inputs", discovered),
            ("adapter", adapter.clone()),
            ("options", options),
            (
                "on_progress",
                invocation
                    .getattr("planning_progress")?
                    .getattr("on_progress")?,
            ),
        ],
    )?;
    let case_name: Bound<'py, PyAny> = request.getattr("case_name")?;
    let plan_output: Bound<'py, PyAny> = call_with(
        &imported(py, TEST_PLAN_MODULE, "build_test_command_plan")?,
        &[
            ("project", context.getattr("project")?),
            ("adapter", adapter),
            ("scope", context.getattr("scope")?),
            ("relations", context.getattr("relations")?),
            ("case_name", case_name.clone()),
        ],
    )?;
    if !case_name.is_none() && !plan_output.getattr("test_entries")?.is_truthy()? {
        let cases: Vec<String> = strings(plan_output.getattr("available_test_case_names")?)?;
        let available: String = if cases.is_empty() {
            "none".to_owned()
        } else {
            cases.join(", ")
        };
        return Err(unknown_case(
            py,
            format!(
                "SQL test case '{}' did not match the selected tests; available cases: {available}",
                case_name.str()?
            ),
        ));
    }
    call_with(
        &imported(py, NATIVE_MODULE, "build_static_pipeline_result")?,
        &[("context", context), ("plan_output", plan_output)],
    )
}

fn inspection_entry(entry: &Bound<'_, PyAny>) -> PyResult<TestInspectionEntry> {
    let case: Bound<'_, PyAny> = entry.getattr("case_name")?;
    let name: String = entry.getattr("name")?.extract()?;
    let label: String = if case.is_none() {
        name
    } else {
        let parent: Bound<'_, PyAny> = entry.getattr("parent_name")?;
        let parent: String = if parent.is_truthy()? {
            parent.extract()?
        } else {
            name
        };
        format!("{parent} [{}]", case.str()?)
    };
    let mut real_models: Vec<String> = Vec::new();
    let mut expected_models: Vec<String> = Vec::new();
    for step in entry.getattr("chain")?.try_iter()? {
        let step: Bound<'_, PyAny> = step?;
        let model: String = step.getattr("model_name")?.extract()?;
        if !step.getattr("expected_cte_sql")?.is_none() {
            expected_models.push(model.clone());
        }
        real_models.push(model);
    }
    Ok(TestInspectionEntry {
        label,
        mocked_sources: strings(entry.getattr("mock_source_names")?)?,
        mocked_refs: strings(entry.getattr("mock_ref_names")?)?,
        mocked_seeds: strings(entry.getattr("mock_seed_names")?)?,
        mocked_dbt_refs: strings(entry.getattr("mock_dbt_ref_names")?)?,
        mocked_table_functions: strings(entry.getattr("mock_table_function_names")?)?,
        real_models,
        expected_models,
    })
}

/// Write the resolved plan without executing it; returns the exit code.
fn inspect(stream: &Bound<'_, PyAny>, plan_output: &Bound<'_, PyAny>) -> PyResult<i32> {
    let entries: Vec<TestInspectionEntry> = plan_output
        .getattr("test_entries")?
        .try_iter()?
        .map(|entry| inspection_entry(&entry?))
        .collect::<PyResult<_>>()?;
    let warnings: Vec<TestPlanWarning> = plan_output
        .getattr("warnings")?
        .try_iter()?
        .map(|warning| {
            let warning: Bound<'_, PyAny> = warning?;
            Ok(TestPlanWarning {
                severity: warning.getattr("severity")?.getattr("value")?.extract()?,
                message: warning.getattr("message")?.str()?.extract()?,
            })
        })
        .collect::<PyResult<_>>()?;
    let (rendered, code) = render_test_inspection(&entries, &warnings);
    stream.call_method1("write", (rendered,))?;
    stream.call_method0("flush")?;
    Ok(code)
}

/// Write the ready header and run the tests with nested progress; returns the results.
fn run_tests<'py>(
    invocation: &Bound<'py, PyAny>,
    pipeline: &Bound<'py, PyAny>,
    concurrency: i64,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = invocation.py();
    let stream: Bound<'py, PyAny> = invocation.getattr("progress_stream")?;
    let use_color: Bound<'py, PyAny> = invocation.getattr("use_color")?;
    let style: CliStyle = CliStyle {
        use_color: use_color.is_truthy()?,
    };
    let plan_output: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let entries: Bound<'py, PyAny> = plan_output.getattr("test_entries")?;
    let test_count: usize = entries.len()?;
    let mut models: BTreeSet<String> = BTreeSet::new();
    for entry in entries.try_iter()? {
        for step in entry?.getattr("chain")?.try_iter()? {
            models.insert(step?.getattr("model_name")?.extract()?);
        }
    }
    let worker_count: i64 = concurrency.min(i64::try_from(test_count).unwrap_or(i64::MAX));
    let progress: Bound<'py, PyAny> = call_with(
        &imported(py, NESTED_PROGRESS_MODULE, "NestedCommandProgressCallbacks")?,
        &[
            ("total", PyInt::new(py, test_count).into_any()),
            ("label", text(py, "test")),
            ("stream", stream.clone()),
            ("use_color", use_color.clone()),
            (
                "name_width",
                PyInt::new(py, name_width(&entries)?).into_any(),
            ),
            ("concurrency", PyInt::new(py, worker_count).into_any()),
        ],
    )?;
    let projector: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "current_native_progress_projector")?.call0()?;
    if !projector.is_none() {
        for entry in entries.try_iter()? {
            call_with(
                &projector.getattr("expect_resource_enrichment")?,
                &[("resource_name", entry?.getattr("name")?)],
            )?;
        }
    }
    stream.call_method1(
        "write",
        (render_test_ready((test_count, models.len()), style),),
    )?;
    stream.call_method0("flush")?;
    let connection: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", invocation.getattr("adapter_name")?),
            ("stream", stream.clone()),
            ("use_color", use_color.clone()),
        ],
    )?;
    let preflight: Bound<'py, PyAny> = call_with(
        &imported(py, STATUS_REPORTER_MODULE, "TransientStatusReporter")?,
        &[("stream", stream), ("use_color", use_color)],
    )?;
    let event_writer: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "ExecutionEventWriter")?.call0()?;
    let relay: Bound<'py, TestCallbackRelay> = Bound::new(
        py,
        TestCallbackRelay {
            progress: progress.unbind(),
            event_writer: event_writer.clone().unbind(),
            plan_output: plan_output.clone().unbind(),
            connection: connection.clone().unbind(),
        },
    )?;
    let executed: PyResult<Vec<Bound<'py, PyAny>>> = (|| {
        let callbacks: Bound<'py, PyAny> = call_with(
            &imported(py, EXECUTOR_PIPELINE_MODELS, "TestPipelineCallbacks")?,
            &[
                (
                    "on_connection_start",
                    connection.getattr("on_connection_start")?,
                ),
                (
                    "on_connection_complete",
                    relay.getattr("on_connection_complete")?,
                ),
                ("on_connection_error", relay.getattr("on_connection_error")?),
                (
                    "on_progress",
                    preflight.getattr("report_preflight_progress")?,
                ),
                ("on_test_start", relay.getattr("on_test_start")?),
                ("on_test_complete", relay.getattr("on_test_complete")?),
            ],
        )?;
        call_with(
            &imported(py, EXECUTOR_RUN_MODULE, "run_test_pipeline")?,
            &[
                ("plan", plan_output),
                (
                    "connection_config",
                    invocation.getattr("connection_config")?,
                ),
                ("adapter", invocation.getattr("adapter")?),
                ("max_concurrency", PyInt::new(py, concurrency).into_any()),
                ("callbacks", callbacks),
                ("run_id", pipeline.getattr("project")?.getattr("run_id")?),
            ],
        )?
        .try_iter()?
        .collect()
    })();
    let closed: PyResult<Bound<'py, PyAny>> = event_writer.call_method0("close");
    let results: Vec<Bound<'py, PyAny>> = executed?;
    closed?;
    Ok(results)
}

/// Write the summary, failures and JSON output; returns the exit code.
fn complete(
    request: &Bound<'_, PyAny>,
    invocation: &Bound<'_, PyAny>,
    results: &[Bound<'_, PyAny>],
) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    let mut failures: Vec<TestFailure> = Vec::new();
    for result in results {
        if result
            .getattr("outcome")?
            .getattr("value")?
            .extract::<String>()?
            == PASS_OUTCOME
        {
            continue;
        }
        failures.push(TestFailure {
            label: test_label(result, "test_name")?,
            error_message: result.getattr("error_message")?.extract()?,
            error_code: result.getattr("error_code")?.extract()?,
            error_help: result.getattr("error_help")?.extract()?,
        });
    }
    let passed: usize = results.len() - failures.len();
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    let style: CliStyle = CliStyle {
        use_color: invocation.getattr("use_color")?.is_truthy()?,
    };
    stream.call_method1(
        "write",
        (render_test_completion(
            (passed, results.len()),
            &failures,
            style,
        ),),
    )?;
    stream.call_method0("flush")?;
    let tuple: Bound<'_, PyAny> = PyTuple::new(py, results)?.into_any();
    let payload: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "format_test_execution_json")?,
        &[("results", tuple)],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_execution_json_output")?,
        &[
            ("payload", payload),
            ("json_output", request.getattr("json_output")?),
            ("json_output_path", request.getattr("json_output_path")?),
        ],
    )?;
    Ok(test_exit_code(passed, results.len()))
}

/// Run one `sqb test` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_test_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let inspect_only: bool = request.getattr("inspect")?.is_truthy()?;
    let invocation: Bound<'_, PyAny> = call_with(
        &imported(py, INVOCATION_MODULE, "resolve_reported_command_invocation")?,
        &[
            ("request", request.clone()),
            (
                "invocation_type",
                imported(py, COMMAND_MODELS, "TestInvocation")?,
            ),
            (
                "require_connection",
                PyBool::new(py, !inspect_only).to_owned().into_any(),
            ),
        ],
    )?;
    let pipeline: Bound<'_, PyAny> = compile_tests(request, &invocation)?;
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    if inspect_only {
        return inspect(&stream, &pipeline.getattr("plan_output")?);
    }
    let requested: Bound<'_, PyAny> = request.getattr("concurrency")?;
    let concurrency: i64 = if requested.is_none() {
        pipeline
            .getattr("project")?
            .getattr("settings")?
            .getattr("concurrency")?
            .extract()?
    } else {
        requested.extract()?
    };
    stream.call_method1("write", ("\n",))?;
    let header: Bound<'_, PyDict> = PyDict::new(py);
    header.set_item("stream", &stream)?;
    header.set_item("command", EXECUTION_COMMAND)?;
    header.set_item("target", py.None())?;
    header.set_item("concurrency", concurrency)?;
    header.set_item("use_color", invocation.getattr("use_color")?)?;
    imported(py, NATIVE_MODULE, "write_execution_header")?.call((), Some(&header))?;
    let results: Vec<Bound<'_, PyAny>> = run_tests(&invocation, &pipeline, concurrency)?;
    call_with(
        &imported(py, RUNTIME_TARGET_MODULE, "write_test_runtime_target")?,
        &[
            (
                "target_dir",
                invocation
                    .getattr("effective_project_dir")?
                    .call_method1("__truediv__", ("target",))?,
            ),
            ("adapter", invocation.getattr("adapter")?),
            ("plan_output", pipeline.getattr("plan_output")?),
            ("results", PyTuple::new(py, &results)?.into_any()),
        ],
    )?;
    complete(request, &invocation, &results)
}

/// Add source and safe typed values only for parameterized test rows.
#[pyfunction]
#[pyo3(signature = (**options))]
fn format_parameterized_test_label(
    py: Python<'_>,
    options: Option<Bound<'_, PyDict>>,
) -> PyResult<String> {
    let arguments: KeywordArguments<'_> = KeywordArguments::read(
        py,
        "format_parameterized_test_label",
        options,
        (
            &[
                "name",
                "source_path",
                "parameter_schema",
                "parameter_values",
            ],
            &[],
        ),
    )?;
    let item: Bound<'_, PyAny> = py.import("types")?.getattr("SimpleNamespace")?.call(
        (),
        Some(&{
            let fields: Bound<'_, PyDict> = PyDict::new(py);
            for field in [
                "name",
                "source_path",
                "parameter_schema",
                "parameter_values",
            ] {
                fields.set_item(field, arguments.value(field)?)?;
            }
            fields
        }),
    )?;
    test_label(&item, "name")
}

/// Resolve one shared width for test rows and nested expectation rows.
#[pyfunction]
fn resolve_test_name_width(test_entries: &Bound<'_, PyAny>) -> PyResult<usize> {
    name_width(test_entries)
}

/// Build nested expectation rows for a completed SQL unit test.
#[pyfunction]
fn build_test_expectation_rows<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    expectation_rows(result)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_test_command, module)?)?;
    module.add_function(wrap_pyfunction!(format_parameterized_test_label, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_test_name_width, module)?)?;
    module.add_function(wrap_pyfunction!(build_test_expectation_rows, module)?)?;
    Ok(())
}
