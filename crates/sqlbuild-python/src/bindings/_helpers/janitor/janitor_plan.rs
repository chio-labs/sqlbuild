//! Display facts of the executor's janitor plan and execution result.

use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::janitor_text::main::render_janitor_completion::render_janitor_completion;
use sqlbuild_core::janitor_text::main::render_janitor_plan::render_janitor_plan;
use sqlbuild_core::janitor_text::models::{
    ArchiveCandidateText, ArchivedRelationText, JanitorPlanText, JanitorResultCounts,
    OldNameViewText, SourceSchemaText,
};

const TIMESTAMP_FORMAT: &str = "%Y-%m-%d %H:%M:%S";
const DATE_FORMAT: &str = "%Y-%m-%d";

fn display_name(item: &Bound<'_, PyAny>) -> PyResult<String> {
    item.call_method0("display_name")?.extract()
}

fn key_name(item: &Bound<'_, PyAny>) -> PyResult<String> {
    display_name(&native_field(item, "key")?)
}

/// `format(value, pattern)`, as an f-string format spec renders a datetime.
fn formatted(value: &Bound<'_, PyAny>, pattern: &str) -> PyResult<String> {
    value
        .py()
        .import("builtins")?
        .getattr("format")?
        .call1((value, pattern))?
        .extract()
}

/// Whole days between `value` and the planning time, or none when either is unknown.
fn age_days(value: &Bound<'_, PyAny>, planned_at: &Bound<'_, PyAny>) -> PyResult<Option<i64>> {
    if value.is_none() || planned_at.is_none() {
        return Ok(None);
    }
    Ok(Some(
        native_field(&planned_at.sub(value)?, "days")?.extract()?,
    ))
}

fn names(items: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    items.try_iter()?.map(|item| key_name(&item?)).collect()
}

fn archived(
    item: &Bound<'_, PyAny>,
    planned_at: &Bound<'_, PyAny>,
) -> PyResult<ArchivedRelationText> {
    let archived_at: Bound<'_, PyAny> = native_field(item, "archived_at")?;
    Ok(ArchivedRelationText {
        name: key_name(item)?,
        archived_in_run: !native_field(item, "original_key")?.is_none(),
        archived_at: formatted(&archived_at, TIMESTAMP_FORMAT)?,
        age_days: age_days(&archived_at, planned_at)?,
        expires_at: formatted(&native_field(item, "expires_at")?, TIMESTAMP_FORMAT)?,
    })
}

fn archived_list(
    items: &Bound<'_, PyAny>,
    planned_at: &Bound<'_, PyAny>,
) -> PyResult<Vec<ArchivedRelationText>> {
    items
        .try_iter()?
        .map(|item| archived(&item?, planned_at))
        .collect()
}

fn old_name_views(views: &Bound<'_, PyAny>) -> PyResult<Vec<OldNameViewText>> {
    let mut read: Vec<OldNameViewText> = Vec::new();
    for view in views.try_iter()? {
        let view: Bound<'_, PyAny> = view?;
        let expires_at: Bound<'_, PyAny> = native_field(&view, "expires_at")?;
        let drop_reason: Bound<'_, PyAny> = native_field(&view, "drop_reason")?;
        read.push(OldNameViewText {
            name: key_name(&view)?,
            destination_model: native_field(&view, "destination_model")?.str()?.extract()?,
            expires_on: if expires_at.is_none() {
                None
            } else {
                Some(formatted(&expires_at, DATE_FORMAT)?)
            },
            drop_reason: if drop_reason.is_none() {
                None
            } else {
                Some(drop_reason.str()?.extract()?)
            },
            occupied: native_field(&view, "occupied")?.is_truthy()?,
            claimed_by: native_field(&view, "claimed_by")?.extract()?,
        });
    }
    Ok(read)
}

fn source_schemas(schemas: &Bound<'_, PyAny>, blocked: bool) -> PyResult<Vec<SourceSchemaText>> {
    let mut read: Vec<SourceSchemaText> = Vec::new();
    for schema in schemas.try_iter()? {
        let schema: Bound<'_, PyAny> = schema?;
        let (suppressed_candidates, suppressed_archive_deletions) = if blocked {
            (
                names(&native_field(&schema, "suppressed_candidates")?)?,
                names(&native_field(&schema, "suppressed_archive_deletions")?)?,
            )
        } else {
            (Vec::new(), Vec::new())
        };
        read.push(SourceSchemaText {
            name: display_name(&schema)?,
            source_names: native_field(&schema, "source_names")?
                .try_iter()?
                .map(|name| name?.str()?.extract())
                .collect::<PyResult<_>>()?,
            suppressed_candidates,
            suppressed_archive_deletions,
        });
    }
    Ok(read)
}

/// The display facts of one executor `JanitorPlan`.
pub(crate) fn janitor_plan_text(plan: &Bound<'_, PyAny>) -> PyResult<JanitorPlanText> {
    let planned_at: Bound<'_, PyAny> = native_field(plan, "planned_at")?;
    let mut archive_candidates: Vec<ArchiveCandidateText> = Vec::new();
    for candidate in native_field(plan, "archive_candidates")?.try_iter()? {
        let candidate: Bound<'_, PyAny> = candidate?;
        let expires_at: Bound<'_, PyAny> = native_field(&candidate, "expires_at")?;
        archive_candidates.push(ArchiveCandidateText {
            name: key_name(&candidate)?,
            archive_name: display_name(&native_field(&candidate, "archive_key")?)?,
            age_days: age_days(&native_field(&candidate, "age_timestamp")?, &planned_at)?,
            expires_now: expires_at.le(native_field(&candidate, "archived_at")?)?,
            expires_at: formatted(&expires_at, TIMESTAMP_FORMAT)?,
        });
    }
    let mut state_prunes: Vec<(String, i64)> = Vec::new();
    for candidate in native_field(plan, "direct_state_prune_candidates")?.try_iter()? {
        let candidate: Bound<'_, PyAny> = candidate?;
        state_prunes.push((
            display_name(&candidate)?,
            native_field(&candidate, "retain_versions")?.extract()?,
        ));
    }
    let mut skipped_relations: Vec<(String, String)> = Vec::new();
    for skipped in native_field(plan, "skipped_relations")?.try_iter()? {
        let skipped: Bound<'_, PyAny> = skipped?;
        skipped_relations.push((
            key_name(&skipped)?,
            native_field(&skipped, "reason")?.str()?.extract()?,
        ));
    }
    let views: Bound<'_, PyAny> = native_field(plan, "old_name_views")?;
    Ok(JanitorPlanText {
        target_name: native_field(plan, "target_name")?.extract()?,
        retention_days: native_field(plan, "retention_days")?.extract()?,
        direct_mode: native_field(plan, "direct_mode")?.is_truthy()?,
        archive_retention_days: native_field(plan, "archive_retention_days")?.extract()?,
        age_metadata_supported: native_field(plan, "age_metadata_supported")?.is_truthy()?,
        scanned_schema_count: native_field(plan, "scanned_schema_count")?.extract()?,
        candidates: names(&native_field(plan, "candidates")?)?,
        archive_candidates,
        archive_deletions: archived_list(
            &native_field(plan, "archive_deletion_candidates")?,
            &planned_at,
        )?,
        retained_archives: archived_list(&native_field(plan, "retained_archives")?, &planned_at)?,
        old_name_drops: old_name_views(&native_field(&views, "drops")?)?,
        old_name_live: old_name_views(&native_field(&views, "live")?)?,
        old_name_missing: old_name_views(&native_field(&views, "missing")?)?,
        query_artifacts: names(&native_field(plan, "query_diff_artifact_candidates")?)?,
        state_prunes,
        skipped_relations,
        skipped_schemas: source_schemas(&native_field(plan, "skipped_schemas")?, false)?,
        blocked_schemas: source_schemas(&native_field(plan, "blocked_schemas")?, true)?,
    })
}

/// How many items an executor `JanitorExecutionResult` changed.
pub(crate) fn janitor_result_counts(result: &Bound<'_, PyAny>) -> PyResult<JanitorResultCounts> {
    let count = |name: &str| -> PyResult<usize> { native_field(result, name)?.len() };
    Ok(JanitorResultCounts {
        archived: count("archived")?,
        deleted: count("deleted")?,
        deleted_archives: count("deleted_archives")?,
        deleted_query_artifacts: count("deleted_query_diff_artifacts")?,
        dropped_old_name_views: count("dropped_old_name_views")?,
        pruned_direct_state: count("pruned_direct_state")?,
    })
}

/// Render one executor janitor plan as the `sqb janitor` preview.
#[pyfunction]
#[pyo3(name = "render_janitor_plan", signature = (*, plan, use_color = false, verbose = false))]
fn render_janitor_plan_text(
    plan: &Bound<'_, PyAny>,
    use_color: bool,
    verbose: bool,
) -> PyResult<String> {
    Ok(render_janitor_plan(
        &janitor_plan_text(plan)?,
        verbose,
        CliStyle { use_color },
    ))
}

/// Render one executor janitor result as the `sqb janitor` completion line.
#[pyfunction]
#[pyo3(
    name = "render_janitor_completion",
    signature = (*, result, elapsed_seconds = None, use_color = false)
)]
fn render_janitor_completion_text(
    result: &Bound<'_, PyAny>,
    elapsed_seconds: Option<f64>,
    use_color: bool,
) -> PyResult<String> {
    Ok(render_janitor_completion(
        &janitor_result_counts(result)?,
        elapsed_seconds,
        false,
        CliStyle { use_color },
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_janitor_plan_text, module)?)?;
    module.add_function(wrap_pyfunction!(render_janitor_completion_text, module)?)
}
