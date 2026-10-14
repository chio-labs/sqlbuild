//! Raw-query `sqb diff`: preparation, artifact materialization, comparison and cleanup.

use std::time::Instant;

use pyo3::exceptions::PyException;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_cli::diff_report::errors::DiffUserError;
use sqlbuild_cli::diff_report::main::effective_max_examples::effective_max_examples;
use sqlbuild_cli::diff_report::main::query_column_problem::query_column_problem;
use sqlbuild_cli::diff_report::main::read_only_query_problem::read_only_query_problem;
use sqlbuild_cli::diff_report::models::QueryShapeFacts;
use sqlbuild_cli::diff_report::types::PhaseSeconds;

use crate::bindings::_helpers::command_runtime::adapters::resolve_cli_adapter;
use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::diff_report::support::{
    call, cli_error, error_text, none, object, progress_line,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const NAMESPACE_MODULE: &str = "sqlbuild._native";
const RUNTIME_MODULE: &str = "sqlbuild._native";
const POLYGLOT_MODULE: &str = "sqlbuild.compiler.sql_analysis.main.import_polyglot_sql";
const COMMAND_MODELS_MODULE: &str = "sqlbuild.cli.commands.models";
const LIFECYCLE_MODULE: &str = "sqlbuild.executor.diff.classes.query_artifact_lifecycle";
const RELATION_LOOKUP_MODULE: &str = "sqlbuild.adapter.relations.main.relation_lookup";
const CURSOR_MODELS_MODULE: &str = "sqlbuild.cursor_algebra.models";
const EXECUTE_QUERY_MODULE: &str = "sqlbuild.executor.diff.main._execute_query";
const DIFF_MODELS_MODULE: &str = "sqlbuild.executor.diff.models";
const DIFF_CONFIG_MODULE: &str = "sqlbuild.executor.diff.main._config";
const NAMESPACELESS_ADAPTERS: [&str; 2] = ["duckdb", "motherduck"];

fn failure(py: Python<'_>, message: String, code: &str, help: Option<&str>) -> PyErr {
    cli_error(
        py,
        "CliUserError",
        &DiffUserError {
            message,
            code: code.to_owned(),
            help: help.map(str::to_owned),
        },
    )
}

fn user_failure(py: Python<'_>, error: DiffUserError) -> PyErr {
    cli_error(py, "CliUserError", &error)
}

/// The adapter of the effective adapter name, resolved for the project directory.
pub(crate) fn project_adapter<'py>(
    discovered: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<(String, Bound<'py, PyAny>)> {
    let py: Python<'py> = discovered.py();
    let name: Bound<'py, PyAny> = call(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", &discovered.getattr("project_config")?),
            ("local_config", &discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = resolve_cli_adapter(&name, project_dir)?;
    Ok((name.extract()?, adapter))
}

fn query_input(
    py: Python<'_>,
    inline: Bound<'_, PyAny>,
    file: Bound<'_, PyAny>,
    label: &str,
) -> PyResult<String> {
    if !inline.is_none() {
        return inline.extract();
    }
    if file.is_none() {
        return Err(failure(
            py,
            format!("raw-query diff requires a {label} query"),
            "C229",
            None,
        ));
    }
    if !file.call_method0("exists")?.is_truthy()? || !file.call_method0("is_file")?.is_truthy()? {
        return Err(failure(
            py,
            format!("{label} query file does not exist: {}", file.str()?),
            "C230",
            None,
        ));
    }
    let keywords: Bound<'_, PyDict> = PyDict::new(py);
    keywords.set_item("encoding", "utf-8")?;
    match file.call_method("read_text", (), Some(&keywords)) {
        Ok(text) => text.extract(),
        Err(error)
            if error.is_instance_of::<pyo3::exceptions::PyOSError>(py)
                || error.is_instance_of::<pyo3::exceptions::PyUnicodeError>(py) =>
        {
            let replacement: PyErr = failure(
                py,
                format!(
                    "{label} query file could not be read as UTF-8: {}",
                    file.str()?
                ),
                "C231",
                None,
            );
            replacement.set_cause(py, Some(error));
            Err(replacement)
        }
        Err(error) => Err(error),
    }
}

fn node_key(node: &Bound<'_, PyAny>) -> PyResult<String> {
    match node.getattr_opt("key")? {
        Some(key) => Ok(key.str()?.to_string().to_lowercase()),
        None => Ok(String::new()),
    }
}

fn read_only_query(
    py: Python<'_>,
    sql: &str,
    label: &str,
    adapter: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let mut normalized: &str = sql.trim();
    if let Some(stripped) = normalized.strip_suffix(';') {
        normalized = stripped.trim_end();
    }
    if normalized.is_empty() {
        return Err(failure(
            py,
            format!("{label} query must not be empty"),
            "C232",
            None,
        ));
    }
    let polyglot: Bound<'_, PyAny> =
        imported(py, POLYGLOT_MODULE, "import_polyglot_sql")?.call0()?;
    if polyglot.is_none() {
        return Err(failure(
            py,
            "raw-query diff requires the bundled SQL parser".to_owned(),
            "C233",
            None,
        ));
    }
    let dialect: Bound<'_, PyAny> = adapter.call_method0("sql_analysis_dialect")?;
    let dialect: Bound<'_, PyAny> = if dialect.is_truthy()? {
        dialect
    } else {
        object(py, "generic")?
    };
    let keywords: Bound<'_, PyDict> = PyDict::new(py);
    keywords.set_item("dialect", dialect)?;
    let expression: Bound<'_, PyAny> =
        match polyglot.call_method("parse_one", (normalized,), Some(&keywords)) {
            Ok(expression) => expression,
            Err(error) if error.is_instance_of::<PyException>(py) => {
                let replacement: PyErr = failure(
                    py,
                    format!(
                        "{label} query is not one valid SQL statement: {}",
                        error_text(py, &error)?
                    ),
                    "C234",
                    None,
                );
                replacement.set_cause(py, Some(error));
                return Err(replacement);
            }
            Err(error) => return Err(error),
        };
    let mut node_keys: Vec<String> = Vec::new();
    let root_key: String = node_key(&expression)?;
    let read_only_root: bool =
        ["except", "intersect", "select", "union", "values"].contains(&root_key.as_str());
    if read_only_root {
        for node in expression.call_method0("walk")?.try_iter()? {
            node_keys.push(node_key(&node?)?);
        }
    }
    let arguments: Bound<'_, PyAny> = expression.getattr_opt("args")?.unwrap_or_else(|| none(py));
    let writes_or_locks: bool = match arguments.downcast::<PyDict>() {
        Ok(arguments) => {
            arguments
                .get_item("into")?
                .is_some_and(|into| !into.is_none())
                || arguments
                    .get_item("locks")?
                    .map_or(Ok(false), |locks| locks.is_truthy())?
        }
        Err(_) => false,
    };
    read_only_query_problem(
        label,
        &QueryShapeFacts {
            root_key,
            node_keys,
            writes_or_locks,
        },
    )
    .map_err(|error| user_failure(py, error))?;
    Ok(normalized.to_owned())
}

/// Resolve raw SQL, the active target namespace, the adapter and its connection.
pub(crate) fn prepare_query_diff<'py>(
    request: &Bound<'py, PyAny>,
    (project_dir, discovered): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let (adapter_name, adapter) = project_adapter(discovered, project_dir)?;
    let selected_target: Bound<'py, PyAny> = request.getattr("selected_target")?;
    let cli_vars: Bound<'py, PyAny> = request.getattr("cli_vars")?;
    let config: Bound<'py, PyAny> = call(
        &imported(py, NATIVE_MODULE, "resolve_project_connection_config")?,
        &[
            ("discovered_inputs", discovered),
            ("project_dir", project_dir),
            ("selected_target", &selected_target),
            ("cli_vars", &cli_vars),
        ],
    )?;
    let database: Bound<'py, PyAny> = if NAMESPACELESS_ADAPTERS.contains(&adapter_name.as_str()) {
        none(py)
    } else {
        config.call_method1("get", ("database",))?
    };
    let namespace: Bound<'py, PyAny> = call(
        &imported(py, NAMESPACE_MODULE, "build_effective_target_namespace")?,
        &[
            ("discovered_inputs", discovered),
            ("selected_target", &selected_target),
            ("connection_database", &database),
            (
                "connection_schema",
                &config.call_method1("get", ("schema",))?,
            ),
            (
                "default_database",
                &adapter.call_method0("default_database")?,
            ),
            ("default_schema", &adapter.call_method0("default_schema")?),
        ],
    )?;
    let (target_name, _target, database, schema): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
    ) = namespace.extract()?;
    if schema.is_none() {
        return Err(failure(
            py,
            "raw-query diff requires an active target schema".to_owned(),
            "C227",
            Some("configure the selected target schema before running the comparison"),
        ));
    }
    let left_sql: String = query_input(
        py,
        request.getattr("left_query")?,
        request.getattr("left_query_file")?,
        "left",
    )?;
    let right_sql: String = query_input(
        py,
        request.getattr("right_query")?,
        request.getattr("right_query_file")?,
        "right",
    )?;
    let left_sql: String = read_only_query(py, &left_sql, "left", &adapter)?;
    let right_sql: String = read_only_query(py, &right_sql, "right", &adapter)?;
    let runtime: Bound<'py, PyTuple> = call(
        &imported(py, RUNTIME_MODULE, "build_effective_runtime_config")?,
        &[
            ("discovered_inputs", discovered),
            ("selected_target", &selected_target),
            ("cli_vars", &cli_vars),
        ],
    )?
    .downcast_into()?;
    let label = |name: &str, default: &str| -> PyResult<String> {
        let value: Bound<'py, PyAny> = request.getattr(name)?;
        let text: String = if value.is_truthy()? {
            value.extract()?
        } else {
            default.to_owned()
        };
        Ok(text.trim().to_owned())
    };
    let verbose: bool = request.getattr("verbose")?.is_truthy()?;
    let examples = |name: &str| -> PyResult<Bound<'py, PyAny>> {
        object(
            py,
            effective_max_examples(request.getattr(name)?.extract()?, verbose),
        )
    };
    call(
        &imported(py, COMMAND_MODELS_MODULE, "QueryDiffPreparation")?,
        &[
            ("adapter", &adapter),
            ("connection_config", &config),
            ("left_sql", &object(py, left_sql)?),
            ("right_sql", &object(py, right_sql)?),
            (
                "left_label",
                &object(py, label("left_label", "left query")?)?,
            ),
            (
                "right_label",
                &object(py, label("right_label", "right query")?)?,
            ),
            ("selected_target", &target_name),
            ("database", &database),
            ("schema", &schema),
            ("run_id", &runtime.get_item(2)?),
            (
                "artifact_ttl",
                &discovered
                    .getattr("project_config")?
                    .getattr("diff")?
                    .getattr("query_artifact_ttl")?,
            ),
            (
                "effective_max_column_examples",
                &examples("max_column_examples")?,
            ),
            (
                "effective_max_row_only_examples",
                &examples("max_row_only_examples")?,
            ),
        ],
    )
}

fn seconds(started: Instant) -> f64 {
    started.elapsed().as_secs_f64()
}

/// `RowDiffSamplingOverride` and the comparison options a request asks for.
pub(crate) fn execution_options<'py>(
    request: &Bound<'py, PyAny>,
    extra: &[(&str, &Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let attribute = |name: &str| request.getattr(name);
    let sampling: Bound<'py, PyAny> = call(
        &imported(py, DIFF_MODELS_MODULE, "RowDiffSamplingOverride")?,
        &[
            ("row_limit", &attribute("sample_rows")?),
            ("seed", &attribute("sample_seed")?),
            ("exhaustive", &attribute("exhaustive")?),
        ],
    )?;
    let tolerances: Bound<'py, PyAny> = call(
        &imported(py, DIFF_CONFIG_MODULE, "parse_cli_tolerance_overrides")?,
        &[("values", &attribute("tolerance_overrides")?)],
    )?;
    let schema_only: Bound<'py, PyAny> = attribute("schema_only")?;
    let collect: Bound<'py, PyAny> = object(py, !schema_only.is_truthy()?)?;
    let mut pairs: Vec<(&str, &Bound<'py, PyAny>)> =
        vec![("schema_only", &schema_only), ("collect_samples", &collect)];
    let columns: Bound<'py, PyAny> = attribute("max_columns")?;
    let key: Bound<'py, PyAny> = attribute("unique_key_override")?;
    let unkeyed: Bound<'py, PyAny> = attribute("unkeyed")?;
    let excluded: Bound<'py, PyAny> = attribute("excluded_columns_override")?;
    pairs.extend([
        ("max_columns", &columns),
        ("sampling_override", &sampling),
        ("unique_key_override", &key),
        ("unkeyed", &unkeyed),
        ("excluded_columns_override", &excluded),
        ("tolerance_overrides", &tolerances),
    ]);
    pairs.extend_from_slice(extra);
    call(
        &imported(py, DIFF_MODELS_MODULE, "DiffExecutionOptions")?,
        &pairs,
    )
}

/// Materialize, compare and clean one raw-query pair; the result and per-phase seconds.
pub(crate) fn execute_query_diff<'py>(
    request: &Bound<'py, PyAny>,
    preparation: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, PhaseSeconds)> {
    let py: Python<'py> = request.py();
    let adapter: Bound<'py, PyAny> = preparation.getattr("adapter")?;
    let total_started: Instant = Instant::now();
    let mut phases: Vec<(String, f64)> = Vec::new();
    progress_line(py, "Query diff connection  START")?;
    let connection_started: Instant = Instant::now();
    let connection: Bound<'py, PyAny> =
        match adapter.call_method1("connect", (preparation.getattr("connection_config")?,)) {
            Ok(connection) => connection,
            Err(error) => {
                progress_line(
                    py,
                    &format!(
                        "Query diff connection  ERROR  ({:.2}s)",
                        seconds(connection_started)
                    ),
                )?;
                progress_line(
                    py,
                    &format!("Query diff total  ERROR  ({:.2}s)", seconds(total_started)),
                )?;
                return Err(error);
            }
        };
    phases.push(("connection".to_owned(), seconds(connection_started)));
    progress_line(
        py,
        &format!("Query diff connection  OK  ({:.2}s)", phases[0].1),
    )?;
    let lifecycle: Bound<'py, PyAny> =
        imported(py, LIFECYCLE_MODULE, "QueryDiffArtifactLifecycle")?;
    let artifact = |side: &str| -> PyResult<Bound<'py, PyAny>> {
        call(
            &lifecycle.getattr("build")?,
            &[
                ("adapter", &adapter),
                ("run_id", &preparation.getattr("run_id")?),
                ("side", &object(py, side)?),
                ("database", &preparation.getattr("database")?),
                ("schema", &preparation.getattr("schema")?),
            ],
        )
    };
    let left: Bound<'py, PyAny> = artifact("left")?;
    let right: Bound<'py, PyAny> = artifact("right")?;
    let mut created: Vec<Bound<'py, PyAny>> = Vec::new();
    let outcome: PyResult<Bound<'py, PyAny>> = compare_artifacts(
        (request, preparation),
        (&connection, &lifecycle),
        (&left, &right),
        (&mut created, &mut phases),
    );
    let cleanup_started: Instant = Instant::now();
    progress_line(py, "Query diff immediate cleanup  START")?;
    let mut cleanup_errors: Vec<PyErr> = Vec::new();
    for item in created.iter().rev() {
        if let Err(error) = call(
            &lifecycle.getattr("cleanup")?,
            &[
                ("adapter", &adapter),
                ("connection", &connection),
                ("artifact", item),
            ],
        ) {
            cleanup_errors.push(error);
        }
    }
    if let Err(error) = adapter.call_method1("close", (&connection,)) {
        cleanup_errors.push(error);
    }
    let cleanup_seconds: f64 = seconds(cleanup_started);
    if cleanup_errors.is_empty() {
        progress_line(
            py,
            &format!(
                "Query diff immediate cleanup  OK  ({} removed; {cleanup_seconds:.2}s)",
                created.len()
            ),
        )?;
    } else {
        progress_line(
            py,
            &format!(
                "Query diff immediate cleanup  ERROR  ({} failed; {cleanup_seconds:.2}s)",
                cleanup_errors.len()
            ),
        )?;
    }
    phases.push(("cleanup".to_owned(), cleanup_seconds));
    let total: f64 = seconds(total_started);
    phases.push(("total".to_owned(), total));
    let status: &str = if outcome.is_err() || !cleanup_errors.is_empty() {
        "ERROR"
    } else {
        "OK"
    };
    progress_line(py, &format!("Query diff total  {status}  ({total:.2}s)"))?;
    if !cleanup_errors.is_empty() {
        return Err(cleanup_errors.remove(0));
    }
    let model: Bound<'py, PyAny> = outcome?;
    if model.is_none() {
        return Err(cli_error(
            py,
            "QueryDiffExecutionError",
            &DiffUserError {
                message: "query diff comparison completed without a result".to_owned(),
                code: "C256".to_owned(),
                help: None,
            },
        ));
    }
    let result: Bound<'py, PyAny> = call(
        &imported(py, DIFF_MODELS_MODULE, "DiffExecutionResult")?,
        &[("model_results", &PyTuple::new(py, [model])?.into_any())],
    )?;
    Ok((result, phases))
}

/// Reconcile, inspect, materialize both sides and compare them; the model result.
fn compare_artifacts<'py>(
    (request, preparation): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (connection, lifecycle): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (left, right): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (created, phases): (&mut Vec<Bound<'py, PyAny>>, &mut Vec<(String, f64)>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let adapter: Bound<'py, PyAny> = preparation.getattr("adapter")?;
    phases.push((
        "reconciliation".to_owned(),
        reconcile(preparation, connection, lifecycle)?,
    ));
    let (expires_at, inspection) = inspect(request, preparation, connection, (left, right))?;
    phases.push(("inspection".to_owned(), inspection));
    progress_line(py, "Query diff materialization  START")?;
    let started: Instant = Instant::now();
    for (artifact, sql) in [(left, "left_sql"), (right, "right_sql")] {
        if let Err(error) = call(
            &lifecycle.getattr("materialize")?,
            &[
                ("adapter", &adapter),
                ("connection", connection),
                ("artifact", artifact),
                ("sql", &preparation.getattr(sql)?),
                ("expires_at", &expires_at),
            ],
        ) {
            progress_line(
                py,
                &format!(
                    "Query diff materialization  ERROR  ({:.2}s)",
                    seconds(started)
                ),
            )?;
            return Err(error);
        }
        created.push(artifact.clone());
    }
    let materialization: f64 = seconds(started);
    phases.push(("materialization".to_owned(), materialization));
    progress_line(
        py,
        &format!(
            "Query diff materialization  OK  ({}; expires {}; {materialization:.2}s)",
            preparation.getattr("schema")?.str()?,
            expires_at.call_method0("isoformat")?.str()?
        ),
    )?;
    progress_line(py, "Query diff comparison  START")?;
    let started: Instant = Instant::now();
    let name: String = format!(
        "{} vs {}",
        preparation.getattr("left_label")?.str()?,
        preparation.getattr("right_label")?.str()?
    );
    let pairs: [(&str, Bound<'py, PyAny>); 3] = [
        (
            "max_column_examples",
            preparation.getattr("effective_max_column_examples")?,
        ),
        (
            "max_row_only_examples",
            preparation.getattr("effective_max_row_only_examples")?,
        ),
        ("comparison_name", object(py, name)?),
    ];
    let extra: Vec<(&str, &Bound<'py, PyAny>)> =
        pairs.iter().map(|(key, value)| (*key, value)).collect();
    let compared: PyResult<Bound<'py, PyAny>> =
        execution_options(request, &extra).and_then(|options| {
            call(
                &imported(py, EXECUTE_QUERY_MODULE, "execute_query_diff")?,
                &[
                    ("adapter", &adapter),
                    ("connection", connection),
                    ("left_relation", &left.getattr("relation")?),
                    ("right_relation", &right.getattr("relation")?),
                    ("options", &options),
                ],
            )
        });
    let comparison: f64 = seconds(started);
    phases.push(("comparison".to_owned(), comparison));
    match compared {
        Ok(model) => {
            progress_line(
                py,
                &format!("Query diff comparison  OK  ({comparison:.2}s)"),
            )?;
            Ok(model)
        }
        Err(error) => {
            progress_line(
                py,
                &format!("Query diff comparison  ERROR  ({comparison:.2}s)"),
            )?;
            Err(error)
        }
    }
}

fn reconcile(
    preparation: &Bound<'_, PyAny>,
    connection: &Bound<'_, PyAny>,
    lifecycle: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    let py: Python<'_> = preparation.py();
    progress_line(py, "Query diff reconciliation  START")?;
    let started: Instant = Instant::now();
    let now: Bound<'_, PyAny> = imported(py, "datetime", "datetime")?
        .call_method1("now", (imported(py, "datetime", "UTC")?,))?;
    let cleaned: PyResult<Bound<'_, PyAny>> = call(
        &lifecycle.getattr("cleanup_expired")?,
        &[
            ("adapter", &preparation.getattr("adapter")?),
            ("connection", connection),
            ("database", &preparation.getattr("database")?),
            ("schema", &preparation.getattr("schema")?),
            ("now", &now),
        ],
    );
    let elapsed: f64 = seconds(started);
    let result: Bound<'_, PyAny> = match cleaned {
        Ok(result) => result,
        Err(error) if error.is_instance_of::<PyException>(py) => {
            progress_line(
                py,
                &format!(
                    "Query diff reconciliation  WARNING  recovery cleanup could not inspect historical ownership evidence: {} ({elapsed:.2}s)",
                    error_text(py, &error)?
                ),
            )?;
            return Ok(elapsed);
        }
        Err(error) => return Err(error),
    };
    progress_line(
        py,
        &format!(
            "Query diff reconciliation  OK  ({} expired; {elapsed:.2}s)",
            result.getattr("cleaned")?.len()?
        ),
    )?;
    for relation in result.getattr("untracked")?.try_iter()? {
        progress_line(
            py,
            &format!(
                "Query diff reconciliation  WARNING  reserved-name relation lacks matching ownership evidence: {}",
                relation?.getattr("name")?.str()?
            ),
        )?;
    }
    Ok(elapsed)
}

fn inspect<'py>(
    request: &Bound<'py, PyAny>,
    preparation: &Bound<'py, PyAny>,
    connection: &Bound<'py, PyAny>,
    artifacts: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<(Bound<'py, PyAny>, f64)> {
    let py: Python<'py> = request.py();
    progress_line(py, "Query diff inspection  START")?;
    let started: Instant = Instant::now();
    match inspect_inputs(request, preparation, connection, artifacts) {
        Ok(ttl) => {
            let elapsed: f64 = seconds(started);
            progress_line(py, &format!("Query diff inspection  OK  ({elapsed:.2}s)"))?;
            let now: Bound<'py, PyAny> = imported(py, "datetime", "datetime")?
                .call_method1("now", (imported(py, "datetime", "UTC")?,))?;
            Ok((ttl.call_method1("add_to", (now,))?, elapsed))
        }
        Err(error) => {
            progress_line(
                py,
                &format!("Query diff inspection  ERROR  ({:.2}s)", seconds(started)),
            )?;
            Err(error)
        }
    }
}

/// Refuse existing artifacts, an invalid TTL and unusable query columns; the parsed TTL.
fn inspect_inputs<'py>(
    request: &Bound<'py, PyAny>,
    preparation: &Bound<'py, PyAny>,
    connection: &Bound<'py, PyAny>,
    (left, right): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let adapter: Bound<'py, PyAny> = preparation.getattr("adapter")?;
    let location = |artifact: &Bound<'py, PyAny>| -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            [
                artifact.getattr("database")?,
                artifact.getattr("schema")?,
                artifact.getattr("name")?,
            ],
        )
    };
    let locations: Bound<'py, PyTuple> = PyTuple::new(py, [location(left)?, location(right)?])?;
    let lookup: Bound<'py, PyAny> = call(
        &imported(py, RELATION_LOOKUP_MODULE, "build_relation_lookup")?,
        &[
            ("adapter", &adapter),
            ("connection", connection),
            ("locations", &locations.into_any()),
        ],
    )?;
    for artifact in [left, right] {
        let exists: Bound<'py, PyAny> = call(
            &lookup.getattr("exists")?,
            &[
                ("database", &artifact.getattr("database")?),
                ("schema", &artifact.getattr("schema")?),
                ("name", &artifact.getattr("name")?),
            ],
        )?;
        if exists.is_truthy()? {
            return Err(failure(
                py,
                format!(
                    "query-diff artifact already exists: {}",
                    artifact.getattr("relation")?.str()?
                ),
                "C245",
                Some("wait for its TTL cleanup or investigate the reserved-name relation"),
            ));
        }
    }
    let ttl: Bound<'py, PyAny> = imported(py, CURSOR_MODELS_MODULE, "Duration")?
        .call_method1("parse", (preparation.getattr("artifact_ttl")?,))?;
    if ttl.is_none() {
        return Err(failure(
            py,
            "diff.query_artifact_ttl must be a positive duration".to_owned(),
            "C228",
            None,
        ));
    }
    let max_columns: Option<i64> = request.getattr("max_columns")?.extract()?;
    for (sql, label) in [("left_sql", "left_label"), ("right_sql", "right_label")] {
        let columns: Vec<String> = call(
            &adapter.getattr("query_column_names")?,
            &[
                ("connection", connection),
                ("sql", &preparation.getattr(sql)?),
            ],
        )?
        .extract()?;
        let label: String = preparation.getattr(label)?.extract()?;
        query_column_problem(&label, &columns, max_columns)
            .map_err(|error| user_failure(py, error))?;
    }
    Ok(ttl)
}
