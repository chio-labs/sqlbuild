//! The run-owned review schema: its name, its target, and its creation and cleanup.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_analysis::review_command::main::review_schema_name::review_schema_name;
use sqlbuild_host::entries::models::ExecutorHost;

use crate::bindings::_helpers::boundary::python_calls::{call_with, keywords};
use crate::bindings::_helpers::command_runtime::connection::resolve_target_connection_config;
use crate::bindings::_helpers::contracts::spec_resolution::resolve_target_config;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::construct::{enum_member, new_record_with};
use crate::bindings::_helpers::records::fields::{field as native_field, replaced};
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::review_command::planning::ReviewSettings;
use crate::bindings::_helpers::review_command::support::{
    boolean, compact_timestamp, none, optional_text, text,
};

/// Where the review builds and where its ownership marker goes.
pub(crate) struct ReviewSchema<'py> {
    pub(crate) name: String,
    pub(crate) database: Option<String>,
    marker_database: Option<String>,
    marker_schema: String,
    run_id: String,
    created_at: Bound<'py, PyAny>,
}

/// The review schema of this run: `<prefix>_<UTC>_<commit>_<run>` in the active target's database.
pub(crate) fn review_schema<'py>(
    (project, discovered): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    settings: &ReviewSettings,
    (created_at, head, run_id): (Bound<'py, PyAny>, &str, &str),
) -> PyResult<ReviewSchema<'py>> {
    let py: Python<'py> = project.py();
    let target: Bound<'py, PyAny> = active_target_config(discovered, &settings.target)?;
    let marker_schema: Option<String> =
        optional_text(&native_field(project, "effective_target_schema")?)?;
    let Some(marker_schema) = marker_schema else {
        return Err(
            crate::bindings::_helpers::review_command::support::review_error(
                py,
                "C771",
                &format!(
                    "target '{}' has no schema to record the review schema in",
                    settings.target
                ),
                Some("set schema on the target in sqlbuild_project.toml"),
            ),
        );
    };
    Ok(ReviewSchema {
        name: review_schema_name(
            &settings.schema_prefix,
            &compact_timestamp(&created_at)?,
            head,
            run_id,
        ),
        database: optional_text(&native_field(&target, "database")?)?,
        marker_database: optional_text(&native_field(project, "effective_target_database")?)?,
        marker_schema,
        run_id: run_id.to_owned(),
        created_at,
    })
}

fn active_target_config<'py>(
    discovered: &Bound<'py, PyAny>,
    target: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    resolve_target_config(
        py,
        &native_field(discovered, "project_config")?,
        &native_field(discovered, "local_config")?,
        &text(py, target),
    )
}

/// `discovered` with a target named after the review schema: the active target's connection and
/// policies, writing only to the review schema and reading managed sources like `--against`.
pub(crate) fn with_review_target<'py>(
    discovered: &Bound<'py, PyAny>,
    settings: &ReviewSettings,
    schema: &ReviewSchema<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let active: Bound<'py, PyAny> = active_target_config(discovered, &settings.target)?;
    let against: Bound<'py, PyAny> = active_target_config(discovered, &settings.against)?;
    let sources_from: Bound<'py, PyAny> = match native_field(&against, "defer_sources_to")? {
        value if !value.is_none() => value,
        _ => text(py, &settings.against),
    };
    let clone_policy: Bound<'py, PyAny> = new_record_with(
        py,
        RecordId::ClonePolicy,
        &[
            ("allow_as_clone_origin", boolean(py, false)),
            ("allow_as_clone_destination", boolean(py, true)),
        ],
    )?;
    let review: Bound<'py, PyAny> = replaced(
        &active,
        &[
            ("schema", text(py, &schema.name)),
            ("loader_schema", text(py, &schema.name)),
            ("defer_sources_to", sources_from),
            ("defer_clone_from", none(py)),
            ("clone", clone_policy),
            (
                "missing_migration_origin",
                enum_member(py, RecordId::MissingMigrationOriginPolicy, "ALLOW")?,
            ),
        ],
    )?;
    let project_config: Bound<'py, PyAny> = native_field(discovered, "project_config")?;
    let targets: Bound<'py, PyDict> = PyDict::new(py);
    targets.update(native_field(&project_config, "targets")?.cast::<pyo3::types::PyMapping>()?)?;
    targets.set_item(&schema.name, review)?;
    let project_config: Bound<'py, PyAny> =
        replaced(&project_config, &[("targets", targets.into_any())])?;
    replaced(discovered, &[("project_config", project_config)])
}

/// The active target's connection config.
pub(crate) fn connection_config<'py>(
    request: &Bound<'py, PyAny>,
    (project_dir, discovered): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    settings: &ReviewSettings,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    resolve_target_connection_config(
        py,
        Some(keywords(
            py,
            &[
                ("discovered_inputs", discovered.clone()),
                ("project_dir", project_dir.clone()),
                ("target_name", text(py, &settings.target)),
                ("cli_vars", native_field(request, "cli_vars")?),
            ],
        )?),
    )
}

fn lifecycle(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    host::entry(py, ExecutorHost::ReviewSchemaLifecycle)
}

/// Record ownership in the active target's state table, then create the review schema.
pub(crate) fn create_review_schema<'py>(
    (adapter, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    schema: &ReviewSchema<'py>,
) -> PyResult<()> {
    let py: Python<'py> = adapter.py();
    let marker: Bound<'py, PyAny> = call_with(
        &host::entry(py, ExecutorHost::ReviewSchemaMarker)?,
        &[
            ("database", optional(py, schema.database.as_deref())),
            ("schema", text(py, &schema.name)),
            (
                "marker_database",
                optional(py, schema.marker_database.as_deref()),
            ),
            ("marker_schema", text(py, &schema.marker_schema)),
            ("run_id", text(py, &schema.run_id)),
        ],
    )?;
    call_with(
        &lifecycle(py)?.getattr("create")?,
        &[
            ("adapter", adapter.clone()),
            ("connection", connection.clone()),
            ("marker", marker),
            ("created_at", schema.created_at.clone()),
        ],
    )?;
    Ok(())
}

/// Drop the review schema and confirm it is gone.
pub(crate) fn drop_review_schema(
    (adapter, connection): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
    schema: &ReviewSchema<'_>,
) -> PyResult<bool> {
    let py: Python<'_> = adapter.py();
    let location = [
        ("adapter", adapter.clone()),
        ("connection", connection.clone()),
        ("database", optional(py, schema.database.as_deref())),
        ("schema", text(py, &schema.name)),
    ];
    call_with(&lifecycle(py)?.getattr("drop")?, &location)?;
    Ok(!call_with(&lifecycle(py)?.getattr("exists")?, &location)?.is_truthy()?)
}

fn optional<'py>(py: Python<'py>, value: Option<&str>) -> Bound<'py, PyAny> {
    value.map_or_else(|| none(py), |value| text(py, value))
}
