//! `sqb freshness`: observe selected source freshness without writing state.

use std::collections::BTreeSet;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::freshness_text::main::freshness_exit_code::freshness_exit_code;
use sqlbuild_core::freshness_text::main::freshness_json::freshness_json;
use sqlbuild_core::freshness_text::main::render_freshness_text::render_freshness_text;
use sqlbuild_core::freshness_text::models::FreshnessSourceResult;

use crate::bindings::_helpers::freshness::freshness_observe::{
    Observer, PreviousState, observe_freshness,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const COLOR_MODULE: &str = "sqlbuild.presentation.main.supports_color";
const REJECT_UNIT_TESTS_MODULE: &str =
    "sqlbuild.compiler.pipeline.main._reject_unit_test_selectors";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const ADAPTERS_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.adapters";
const CONNECTION_MODULE: &str = "sqlbuild._native";
const GRAPH_SELECTION_MODULE: &str = "sqlbuild.compiler.pipeline.main._project_graph_selection";
const UPSTREAM_MODULE: &str = "sqlbuild.compiler.planner.main.selection._upstream";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const RELATION_LOOKUP_MODULE: &str = "sqlbuild.adapter.relations.main.relation_lookup";
const STATE_READ_MODULE: &str = "sqlbuild.compiler.source_freshness.main.read";
const STATE_TABLE_NAME: &str = "_sqlbuild_source_freshness";
const STALE_REQUIRES_STATE_MESSAGE: &str = "freshness --fail-on-stale requires --state";
const STALE_REQUIRES_STATE_CODE: &str = "C238";

fn imported<'py>(py: Python<'py>, module: &str, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import(module)?.getattr(name)
}

fn keywords<'py>(
    py: Python<'py>,
    items: &[(&str, &Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyDict>> {
    let dict: Bound<'py, PyDict> = PyDict::new(py);
    for (name, value) in items {
        dict.set_item(*name, value)?;
    }
    Ok(dict)
}

fn user_error(py: Python<'_>, (message, code): (&str, &str)) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", code)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn write(py: Python<'_>, text: &str) -> PyResult<()> {
    py.import("sys")?
        .getattr("stdout")?
        .call_method1("write", (text,))?;
    Ok(())
}

/// Names of the sources among `keys` and their upstream closures.
fn source_names_for_keys(
    graph: &Bound<'_, PyAny>,
    keys: &Bound<'_, PyAny>,
) -> PyResult<BTreeSet<String>> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    let py: Python<'_> = graph.py();
    let source_type: Bound<'_, PyAny> =
        imported(py, COMPILE_TYPES_MODULE, "CompiledResourceType")?.getattr("SOURCE")?;
    let expand: Bound<'_, PyAny> = imported(py, UPSTREAM_MODULE, "expand_project_upstream_keys")?;
    let upstream_deps: Bound<'_, PyAny> = graph.getattr("upstream_deps")?;
    for key in keys.try_iter()? {
        let key: Bound<'_, PyAny> = key?;
        let upstream: Bound<'_, PyAny> = expand.call(
            (),
            Some(&keywords(
                py,
                &[("key", &key), ("upstream_deps", &upstream_deps)],
            )?),
        )?;
        for candidate in std::iter::once(Ok(key.clone())).chain(upstream.try_iter()?) {
            let candidate: Bound<'_, PyAny> = candidate?;
            if candidate.getattr("resource_type")?.eq(&source_type)? {
                names.insert(candidate.getattr("name")?.extract()?);
            }
        }
    }
    Ok(names)
}

fn graph_keys<'py>(
    graph: &Bound<'py, PyAny>,
    selectors: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = graph.py();
    let empty: Bound<'py, PyAny> = PyTuple::empty(py).into_any();
    imported(py, GRAPH_SELECTION_MODULE, "select_project_graph")?.call(
        (),
        Some(&keywords(
            py,
            &[("graph", graph), ("select", selectors), ("exclude", &empty)],
        )?),
    )
}

/// Selected source names, sorted: selected or all keys and their upstream sources, minus excluded.
fn selected_source_names(
    graph: &Bound<'_, PyAny>,
    (select, exclude): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
) -> PyResult<Vec<String>> {
    let selected_keys: Bound<'_, PyAny> = if select.is_truthy()? {
        graph_keys(graph, select)?
    } else {
        graph.getattr("all_keys")?.call_method0("values")?
    };
    let selected: BTreeSet<String> = source_names_for_keys(graph, &selected_keys)?;
    let excluded: BTreeSet<String> = if exclude.is_truthy()? {
        source_names_for_keys(graph, &graph_keys(graph, exclude)?)?
    } else {
        BTreeSet::new()
    };
    Ok(selected.difference(&excluded).cloned().collect())
}

/// Latest direct freshness state records, by identity, across the project's target schemas.
fn previous_records<'py>(
    adapter: &Bound<'py, PyAny>,
    connection: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = adapter.py();
    let mut database: Option<Bound<'py, PyAny>> = None;
    let mut schemas: BTreeSet<String> = BTreeSet::new();
    for collection in ["models", "seeds", "functions"] {
        for item in project.getattr(collection)?.try_iter()? {
            let destination: Bound<'py, PyAny> = item?.getattr("destination")?;
            let destination_database: Bound<'py, PyAny> = destination.getattr("database")?;
            if database.is_none() && !destination_database.is_none() {
                database = Some(destination_database);
            }
            let schema: Bound<'py, PyAny> = destination.getattr("schema")?;
            if !schema.is_none() {
                schemas.insert(schema.extract()?);
            }
        }
    }
    let database: Bound<'py, PyAny> = database.unwrap_or_else(|| py.None().into_bound(py));
    let locations: Vec<Bound<'py, PyTuple>> = schemas
        .iter()
        .map(|schema| {
            PyTuple::new(
                py,
                [
                    database.clone(),
                    PyString::new(py, schema).into_any(),
                    PyString::new(py, STATE_TABLE_NAME).into_any(),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    let lookup: Bound<'py, PyAny> = imported(py, RELATION_LOOKUP_MODULE, "build_relation_lookup")?
        .call(
            (),
            Some(&keywords(
                py,
                &[
                    ("adapter", adapter),
                    ("connection", connection),
                    ("locations", &PyTuple::new(py, locations)?.into_any()),
                ],
            )?),
        )?;
    let read: Bound<'py, PyAny> = imported(py, STATE_READ_MODULE, "read_latest_source_freshness")?;
    let records: Bound<'py, PyDict> = PyDict::new(py);
    for schema in &schemas {
        let exists: Bound<'py, PyDict> = keywords(py, &[("database", &database)])?;
        exists.set_item("schema", schema)?;
        exists.set_item("name", STATE_TABLE_NAME)?;
        let options: Bound<'py, PyDict> = keywords(
            py,
            &[
                ("connection", connection),
                ("execute", &adapter.getattr("execute")?),
                (
                    "table_exists",
                    &lookup.call_method("exists", (), Some(&exists))?,
                ),
                ("database", &database),
                (
                    "render_qualified_name",
                    &adapter.getattr("render_qualified_name")?,
                ),
                (
                    "render_read_latest_sql",
                    &adapter.getattr("render_read_latest_source_freshness_sql")?,
                ),
            ],
        )?;
        options.set_item("schema", schema)?;
        records.update(
            read.call((), Some(&options))?
                .getattr("records")?
                .downcast()?,
        )?;
    }
    Ok(records)
}

/// Connect, read previous state when requested, observe, and close the connection.
fn observe(
    request: &Bound<'_, PyAny>,
    (discovered, project_dir): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
    (adapter, graph): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
    names: &[String],
) -> PyResult<Vec<FreshnessSourceResult>> {
    let py: Python<'_> = adapter.py();
    let connection_config: Bound<'_, PyAny> =
        imported(py, CONNECTION_MODULE, "resolve_project_connection_config")?.call(
            (),
            Some(&keywords(
                py,
                &[
                    ("discovered_inputs", discovered),
                    ("project_dir", project_dir),
                    ("selected_target", &request.getattr("selected_target")?),
                    ("cli_vars", &request.getattr("cli_vars")?),
                ],
            )?),
        )?;
    let connection: Bound<'_, PyAny> = adapter.call_method1("connect", (connection_config,))?;
    let observed = (|| {
        let project: Bound<'_, PyAny> = graph.getattr("project")?;
        let by_identity: Option<Bound<'_, PyAny>> =
            if request.getattr("compare_state")?.extract::<bool>()? {
                Some(previous_records(adapter, &connection, &project)?.into_any())
            } else {
                None
            };
        let sources: Vec<Bound<'_, PyAny>> = project
            .getattr("sources")?
            .try_iter()?
            .map(|source| source?.getattr("source_entry"))
            .collect::<PyResult<_>>()?;
        let observed_at: Bound<'_, PyAny> = imported(py, "datetime", "datetime")?
            .call_method1("now", (imported(py, "datetime", "UTC")?,))?;
        let observer: Observer<'_> = Observer {
            adapter: adapter.clone(),
            connection: connection.clone(),
            observed_at,
        };
        let state: PreviousState<'_> = PreviousState { by_identity };
        observe_freshness(
            &observer,
            (&PyTuple::new(py, sources)?.into_any(), names, &[]),
            (project.getattr("run_id")?.extract()?, &state),
        )
    })();
    let closed: PyResult<Bound<'_, PyAny>> = adapter.call_method1("close", (&connection,));
    let results: Vec<FreshnessSourceResult> = observed?;
    closed?;
    Ok(results)
}

fn write_json_output(
    py: Python<'_>,
    payload: &str,
    (json_output, json_output_path): (bool, &Bound<'_, PyAny>),
) -> PyResult<()> {
    let options: Bound<'_, PyDict> = keywords(py, &[("json_output_path", json_output_path)])?;
    options.set_item("payload", format!("{payload}\n"))?;
    options.set_item("json_output", json_output)?;
    imported(py, NATIVE_MODULE, "write_execution_json_output")?.call((), Some(&options))?;
    Ok(())
}

/// Run one `sqb freshness` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_freshness_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let fail_on_stale: bool = request.getattr("fail_on_stale")?.extract()?;
    let fail_on_error: bool = request.getattr("fail_on_error")?.extract()?;
    if fail_on_stale && !request.getattr("compare_state")?.extract::<bool>()? {
        return Err(user_error(
            py,
            (STALE_REQUIRES_STATE_MESSAGE, STALE_REQUIRES_STATE_CODE),
        ));
    }
    let project_dir: Bound<'_, PyAny> = match request.getattr("project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let discovered: Bound<'_, PyAny> = imported(py, NATIVE_MODULE, "discover_project_inputs")?
        .call((), Some(&keywords(py, &[("project_dir", &project_dir)])?))?;
    let select: Bound<'_, PyAny> = request.getattr("select")?;
    let exclude: Bound<'_, PyAny> = request.getattr("exclude")?;
    imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?.call(
        (),
        Some(&keywords(
            py,
            &[
                ("select", &select),
                ("exclude", &exclude),
                ("discovered_inputs", &discovered),
            ],
        )?),
    )?;
    let adapter_name: Bound<'_, PyAny> =
        imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?.call(
            (),
            Some(&keywords(
                py,
                &[
                    ("project_config", &discovered.getattr("project_config")?),
                    ("local_config", &discovered.getattr("local_config")?),
                ],
            )?),
        )?;
    let adapter: Bound<'_, PyAny> = imported(py, ADAPTERS_MODULE, "resolve_adapter")?.call(
        (),
        Some(&keywords(
            py,
            &[
                ("adapter_name", &adapter_name),
                ("project_dir", &project_dir),
            ],
        )?),
    )?;
    let graph: Bound<'_, PyAny> = imported(py, NATIVE_MODULE, "build_project_graph")?.call(
        (),
        Some(&keywords(
            py,
            &[
                ("discovered_inputs", &discovered),
                ("adapter", &adapter),
                ("selected_target", &request.getattr("selected_target")?),
                ("no_sql_validation", &request.getattr("no_sql_validation")?),
                ("cli_vars", &request.getattr("cli_vars")?),
            ],
        )?),
    )?;
    let names: Vec<String> = selected_source_names(&graph, (&select, &exclude))?;
    let results: Vec<FreshnessSourceResult> = if names.is_empty() {
        Vec::new()
    } else {
        observe(
            request,
            (&discovered, &project_dir),
            (&adapter, &graph),
            &names,
        )?
    };
    let payload: String =
        freshness_json(&results).map_err(|error| PyValueError::new_err(format!("{error:?}")))?;
    let json_output_path: Bound<'_, PyAny> = request.getattr("json_output_path")?;
    if request.getattr("json_output")?.extract::<bool>()? {
        write_json_output(py, &payload, (true, &json_output_path))?;
    } else {
        if !json_output_path.is_none() {
            write_json_output(py, &payload, (false, &json_output_path))?;
        }
        let use_color: bool = !request.getattr("no_color")?.extract::<bool>()?
            && imported(py, COLOR_MODULE, "supports_color")?
                .call0()?
                .extract::<bool>()?;
        write(py, &render_freshness_text(&results, CliStyle { use_color }))?;
    }
    Ok(freshness_exit_code(
        &results,
        (fail_on_stale, fail_on_error),
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_freshness_command, module)?)?;
    Ok(())
}
