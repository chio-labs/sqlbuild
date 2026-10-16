//! Execute the prepared clone plan and propagate fingerprints.

use std::collections::HashMap;
use std::time::Instant;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyFrozenSet, PyString};
use sqlbuild_core::clone_text::main::clone_relation_flow_text::clone_relation_flow_text;
use sqlbuild_core::clone_text::models::FingerprintProgress;

use crate::bindings::_helpers::clone::clone_command::Invocation;
use crate::bindings::_helpers::clone::clone_progress::{
    CloneFingerprintReporter, CloneItemPrinter,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS: &str = "sqlbuild._native";
const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";
const CLONE_MODELS: &str = "sqlbuild.executor.clone.models";
const RETENTION_REQUESTS_MODULE: &str = "sqlbuild.executor.clone.main._build_retention_requests";
const TRANSIENT_MODELS_MODULE: &str =
    "sqlbuild.executor.clone.main._build_destination_transient_models";
const FINGERPRINTING_MODULE: &str = "sqlbuild.executor.clone.main._fingerprinting";
const EXECUTE_MODULE: &str = "sqlbuild.executor.clone.main.execute";
const TARGET_CONFIG_MODULE: &str = "sqlbuild._native";
const CONTRACT_TYPES: &str = "sqlbuild._native";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";
const DESTINATION_ENTRY_GROUPS: [&str; 4] = [
    "destination_source_entries",
    "destination_model_entries",
    "destination_seed_entries",
    "destination_function_entries",
];
const ORIGIN_ENTRY_GROUPS: [&str; 3] = [
    "origin_source_entries",
    "origin_model_entries",
    "origin_seed_entries",
];

/// The pipeline's plan entries of `groups`, in order.
fn entries<'py>(pipeline: &Bound<'py, PyAny>, groups: &[&str]) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut found: Vec<Bound<'py, PyAny>> = Vec::new();
    for group in groups {
        for entry in pipeline.getattr(*group)?.try_iter()? {
            found.push(entry?);
        }
    }
    Ok(found)
}

/// The number of destination entries, which the header counts.
pub(crate) fn destination_entry_count(pipeline: &Bound<'_, PyAny>) -> PyResult<usize> {
    Ok(entries(pipeline, &DESTINATION_ENTRY_GROUPS)?.len())
}

/// Each destination entry's resource type by name.
pub(crate) fn resource_types_by_name(
    pipeline: &Bound<'_, PyAny>,
) -> PyResult<HashMap<String, String>> {
    entries(pipeline, &DESTINATION_ENTRY_GROUPS)?
        .iter()
        .map(|entry| {
            Ok((
                entry.getattr("name")?.extract()?,
                entry
                    .getattr("key")?
                    .getattr("resource_type")?
                    .str()?
                    .extract()?,
            ))
        })
        .collect()
}

fn relation_text(entry: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let destination: Bound<'_, PyAny> = entry.getattr("destination")?;
    let qualified: Bound<'_, PyAny> = destination.getattr("qualified_name")?;
    let relation: Bound<'_, PyAny> = if qualified.is_truthy()? {
        qualified
    } else {
        destination.getattr("name")?
    };
    if relation.is_none() {
        return Ok(None);
    }
    relation.extract().map(Some)
}

/// The widest plain relation flow among the destination entries.
fn relation_width(pipeline: &Bound<'_, PyAny>) -> PyResult<usize> {
    let mut origins: HashMap<String, Option<String>> = HashMap::new();
    for entry in entries(pipeline, &ORIGIN_ENTRY_GROUPS)? {
        origins.insert(entry.getattr("name")?.extract()?, relation_text(&entry)?);
    }
    let mut width: usize = 0;
    for entry in entries(pipeline, &DESTINATION_ENTRY_GROUPS)? {
        let name: String = entry.getattr("name")?.extract()?;
        let destination: Option<String> = relation_text(&entry)?;
        let origin: Option<&str> = origins.get(&name).and_then(Option::as_deref);
        let flow: String = clone_relation_flow_text(&name, (origin, destination.as_deref()));
        width = width.max(flow.chars().count());
    }
    Ok(width)
}

/// Destination relation locations of every planned entry and of each source table.
fn dependency_locations<'py>(
    pipeline: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = pipeline.py();
    let locations: Bound<'py, PyDict> = PyDict::new(py);
    for entry in entries(pipeline, &DESTINATION_ENTRY_GROUPS)? {
        locations.set_item(entry.getattr("key")?, entry.getattr("destination")?)?;
    }
    let plan: Bound<'py, PyAny> = pipeline.getattr("clone_plan")?;
    let read_map: Bound<'py, PyAny> = plan.getattr("source_read_map")?;
    let source_map: Bound<'py, PyAny> = if read_map.is_truthy()? {
        read_map
    } else {
        plan.getattr("source_map")?
    };
    let key_class: Bound<'py, PyAny> = imported(py, COMPILE_MODELS, "CompiledObjectKey")?;
    let location_class: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS, "CompiledRelationLocation")?;
    let source_type: Bound<'py, PyAny> =
        imported(py, COMPILE_TYPES, "CompiledResourceType")?.getattr("SOURCE")?;
    for pair in source_map.call_method0("items")?.try_iter()? {
        let (name, source): (Bound<'py, PyAny>, Bound<'py, PyAny>) = pair?.extract()?;
        let table: Bound<'py, PyAny> = source.getattr("table")?;
        if table.is_none() {
            continue;
        }
        let place = [
            ("database", source.getattr("database")?),
            ("schema", source.getattr("schema")?),
            ("name", table.clone()),
        ];
        let rendered: Bound<'py, PyAny> =
            call_with(&adapter.getattr("render_qualified_name")?, &place)?;
        let qualified: Bound<'py, PyAny> = if rendered.is_truthy()? {
            rendered
        } else {
            table
        };
        let [database, schema, table] = place;
        let location: Bound<'py, PyAny> = call_with(
            &location_class,
            &[database, schema, table, ("qualified_name", qualified)],
        )?;
        locations.set_item(key_class.call1((&source_type, name))?, location)?;
    }
    Ok(locations)
}

fn target_config<'py>(invocation: &Invocation<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.adapter.py();
    call_with(
        &imported(py, TARGET_CONFIG_MODULE, "resolve_target_config")?,
        &[
            (
                "project_config",
                invocation.discovered.getattr("project_config")?,
            ),
            (
                "local_config",
                invocation.discovered.getattr("local_config")?,
            ),
            (
                "target_name",
                PyString::new(py, &invocation.destination).into_any(),
            ),
        ],
    )
}

/// The executor input for the whole clone, streaming items through `on_item`.
fn execution_input<'py>(
    invocation: &Invocation<'py>,
    (pipeline, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (hard_copy, on_item): (Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = pipeline.py();
    let project: Bound<'py, PyAny> = pipeline.getattr("destination_project")?;
    let plan: Bound<'py, PyAny> = pipeline.getattr("clone_plan")?;
    let config: Bound<'py, PyAny> = target_config(invocation)?;
    let selected: Vec<Bound<'py, PyAny>> = pipeline
        .getattr("destination_model_entries")?
        .try_iter()?
        .map(|entry| entry?.getattr("name"))
        .collect::<PyResult<_>>()?;
    let retention: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            RETENTION_REQUESTS_MODULE,
            "build_destination_retention_requests",
        )?,
        &[
            ("project", project.clone()),
            (
                "adapter_name",
                PyString::new(py, &invocation.adapter_name).into_any(),
            ),
            (
                "selected_model_names",
                PyFrozenSet::new(py, selected)?.into_any(),
            ),
            (
                "namespace_owned",
                config.getattr("owns_time_travel_retention_namespace")?,
            ),
        ],
    )?;
    let allow_decrease: bool = config
        .getattr("time_travel_retention_decrease")?
        .eq(imported(py, CONTRACT_TYPES, "RetentionDecreasePolicy")?.getattr("ALLOW")?)?;
    let source_entries: Bound<'py, PyAny> = call_with(
        &imported(py, CLONE_MODELS, "CloneSourceEntries")?,
        &[
            ("origin", pipeline.getattr("origin_source_entries")?),
            (
                "destination",
                pipeline.getattr("destination_source_entries")?,
            ),
        ],
    )?;
    let transient: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            TRANSIENT_MODELS_MODULE,
            "build_destination_transient_models",
        )?,
        &[("project", project.clone())],
    )?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![("source_entries", source_entries)];
    for group in [
        "origin_model_entries",
        "destination_model_entries",
        "origin_seed_entries",
        "destination_seed_entries",
        "destination_function_entries",
    ] {
        fields.push((group, pipeline.getattr(group)?));
    }
    fields.extend([
        ("execution_order", plan.getattr("execution_order")?),
        ("adapter", invocation.adapter.clone()),
        ("destination_connection", connection.clone()),
        ("hard_copy", hard_copy),
        ("run_id", project.getattr("run_id")?),
        (
            "query_change_tracking",
            project
                .getattr("settings")?
                .getattr("query_change_tracking")?,
        ),
        ("upstream_deps", plan.getattr("upstream_deps")?),
        (
            "dependency_locations",
            dependency_locations(pipeline, &invocation.adapter)?.into_any(),
        ),
        ("destination_transient_models", transient),
        ("destination_retention_requests", retention),
        (
            "allow_namespace_retention_decrease",
            PyBool::new(py, allow_decrease).to_owned().into_any(),
        ),
        ("on_item", on_item),
    ]);
    call_with(&imported(py, CLONE_MODELS, "CloneExecutionInput")?, &fields)
}

/// Copy fingerprints of the cloned relations, reporting what was not confirmed on failure.
fn copy_fingerprints<'py>(
    invocation: &Invocation<'py>,
    (pipeline, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    result: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py: Python<'py> = pipeline.py();
    let reporter: Bound<'py, CloneFingerprintReporter> = Bound::new(
        py,
        CloneFingerprintReporter {
            stream: invocation.stream.clone().unbind(),
            style: invocation.style,
            progress: FingerprintProgress::default(),
        },
    )?;
    let project: Bound<'py, PyAny> = pipeline.getattr("destination_project")?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![("result", result.clone())];
    for group in [
        "origin_model_entries",
        "destination_model_entries",
        "origin_seed_entries",
        "destination_seed_entries",
    ] {
        fields.push((group, pipeline.getattr(group)?));
    }
    fields.extend([
        ("adapter", invocation.adapter.clone()),
        ("destination_connection", connection.clone()),
        ("run_id", project.getattr("run_id")?),
        (
            "query_change_tracking",
            project
                .getattr("settings")?
                .getattr("query_change_tracking")?,
        ),
        ("on_progress", reporter.clone().into_any()),
    ]);
    let lifecycle: Bound<'py, PyAny> = call_with(
        &imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?,
        &[
            ("operation_kind", PyString::new(py, "clone").into_any()),
            (
                "operation_name",
                PyString::new(py, "clone_finalization").into_any(),
            ),
        ],
    )?;
    let copied: PyResult<Bound<'py, PyAny>> = within(&lifecycle, |_| {
        call_with(
            &imported(py, FINGERPRINTING_MODULE, "copy_clone_fingerprints")?,
            &fields,
        )
    });
    if let Err(error) = copied {
        reporter.borrow().write_interrupted(py)?;
        return Err(error);
    }
    Ok(())
}

/// Execute the clone, streaming items, then copy fingerprints; returns the result and elapsed seconds.
pub(crate) fn execute_clone_plan<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
    (pipeline, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<(Bound<'py, PyAny>, f64)> {
    let py: Python<'py> = pipeline.py();
    let started: Instant = Instant::now();
    let event_writer: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ExecutionEventWriter")?,
        &[("path", request.getattr("event_output_path")?)],
    )?;
    let printer: Py<CloneItemPrinter> = Py::new(
        py,
        CloneItemPrinter {
            stream: invocation.stream.clone().unbind(),
            style: invocation.style,
            relation_width: relation_width(pipeline)?,
            event_writer: event_writer.clone().unbind(),
            resource_types: resource_types_by_name(pipeline)?,
        },
    )?;
    let executed: PyResult<Bound<'py, PyAny>> = (|| {
        let input: Bound<'py, PyAny> = execution_input(
            invocation,
            (pipeline, connection),
            (
                request.getattr("hard_copy")?,
                printer.into_bound(py).into_any(),
            ),
        )?;
        call_with(
            &imported(py, EXECUTE_MODULE, "execute_clone")?,
            &[("inputs", input)],
        )
    })();
    let closed: PyResult<Bound<'py, PyAny>> = event_writer.call_method0("close");
    let result: Bound<'py, PyAny> = executed?;
    closed?;
    copy_fingerprints(invocation, (pipeline, connection), &result)?;
    Ok((result, started.elapsed().as_secs_f64()))
}
