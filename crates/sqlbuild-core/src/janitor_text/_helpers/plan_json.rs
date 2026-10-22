//! The JSON payload of `sqb janitor --json`.

use crate::janitor_text::constants::{DROP_EARLY, DROP_EXPIRED};
use crate::janitor_text::models::{
    JanitorItemText, JanitorPlanText, JanitorResultCounts, JanitorRunText, OldNameViewText,
    SourceSchemaText,
};
use crate::json::models::{JsonInteger, JsonValue};

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn optional_text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, text)
}

fn texts(values: &[String]) -> JsonValue {
    JsonValue::Array(values.iter().map(|value| text(value)).collect())
}

fn integer(value: impl ToString) -> JsonValue {
    JsonInteger::parse(&value.to_string()).map_or(JsonValue::Null, JsonValue::Integer)
}

fn optional_integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, integer)
}

fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        fields
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

/// A preview `YYYY-MM-DD HH:MM:SS` UTC time as ISO 8601.
fn utc_timestamp(value: &str) -> JsonValue {
    if value.is_empty() {
        return JsonValue::Null;
    }
    text(&format!("{}Z", value.replacen(' ', "T", 1)))
}

fn old_name_view(view: &OldNameViewText, planned: &str) -> JsonValue {
    let action: &str = match (planned, view.drop_reason.as_deref()) {
        ("drop", Some(DROP_EARLY | DROP_EXPIRED)) => "drop",
        ("live", _) => "keep",
        _ => "record_dropped",
    };
    object(vec![
        ("name", text(&view.name)),
        ("destination_model", text(&view.destination_model)),
        ("expires_on", optional_text(view.expires_on.as_deref())),
        ("action", text(action)),
        ("drop_reason", optional_text(view.drop_reason.as_deref())),
        ("occupied", JsonValue::Bool(view.occupied)),
        ("claimed_by", optional_text(view.claimed_by.as_deref())),
    ])
}

fn source_schema(schema: &SourceSchemaText, blocked: bool) -> JsonValue {
    let mut fields: Vec<(&str, JsonValue)> = vec![
        ("name", text(&schema.name)),
        ("source_names", texts(&schema.source_names)),
    ];
    if blocked {
        fields.push((
            "suppressed_candidates",
            texts(&schema.suppressed_candidates),
        ));
        fields.push((
            "suppressed_archive_deletions",
            texts(&schema.suppressed_archive_deletions),
        ));
    }
    object(fields)
}

/// Every planned action, retained archive and skipped object of the plan.
pub(crate) fn plan_payload(plan: &JanitorPlanText) -> JsonValue {
    let views: Vec<JsonValue> = plan
        .old_name_drops
        .iter()
        .map(|view| old_name_view(view, "drop"))
        .chain(
            plan.old_name_live
                .iter()
                .map(|view| old_name_view(view, "live")),
        )
        .chain(
            plan.old_name_missing
                .iter()
                .map(|view| old_name_view(view, "missing")),
        )
        .collect();
    object(vec![
        ("direct_mode", JsonValue::Bool(plan.direct_mode)),
        ("retention_days", integer(plan.retention_days)),
        (
            "archive_retention_days",
            integer(plan.archive_retention_days),
        ),
        (
            "age_metadata_supported",
            JsonValue::Bool(plan.age_metadata_supported),
        ),
        ("schemas_scanned", integer(plan.scanned_schema_count)),
        ("eligible_for_deletion", texts(&plan.candidates)),
        (
            "relations_to_archive",
            JsonValue::Array(
                plan.archive_candidates
                    .iter()
                    .map(|candidate| {
                        object(vec![
                            ("name", text(&candidate.name)),
                            ("archive_name", text(&candidate.archive_name)),
                            ("age_days", optional_integer(candidate.age_days)),
                            ("expires_at", utc_timestamp(&candidate.expires_at)),
                            ("deleted_in_run", JsonValue::Bool(candidate.expires_now)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "archives_to_delete",
            JsonValue::Array(
                plan.archive_deletions
                    .iter()
                    .map(|archive| {
                        object(vec![
                            ("name", text(&archive.name)),
                            ("archived_in_run", JsonValue::Bool(archive.archived_in_run)),
                            ("archived_at", utc_timestamp(&archive.archived_at)),
                            ("age_days", optional_integer(archive.age_days)),
                            ("expires_at", utc_timestamp(&archive.expires_at)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "retained_archives",
            JsonValue::Array(
                plan.retained_archives
                    .iter()
                    .map(|archive| {
                        object(vec![
                            ("name", text(&archive.name)),
                            ("archived_at", utc_timestamp(&archive.archived_at)),
                            ("expires_at", utc_timestamp(&archive.expires_at)),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("old_name_views", JsonValue::Array(views)),
        ("query_artifacts", texts(&plan.query_artifacts)),
        (
            "direct_state_prunes",
            JsonValue::Array(
                plan.state_prunes
                    .iter()
                    .map(|(name, versions)| {
                        object(vec![
                            ("name", text(name)),
                            ("retain_versions", integer(*versions)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "skipped_objects",
            JsonValue::Array(
                plan.skipped_relations
                    .iter()
                    .map(|(name, reason)| {
                        object(vec![("name", text(name)), ("reason", text(reason))])
                    })
                    .collect(),
            ),
        ),
        (
            "skipped_schemas",
            JsonValue::Array(
                plan.skipped_schemas
                    .iter()
                    .map(|schema| source_schema(schema, false))
                    .collect(),
            ),
        ),
        (
            "blocked_schemas",
            JsonValue::Array(
                plan.blocked_schemas
                    .iter()
                    .map(|schema| source_schema(schema, true))
                    .collect(),
            ),
        ),
    ])
}

fn counts_payload(counts: &JanitorResultCounts) -> JsonValue {
    object(vec![
        ("archived", integer(counts.archived)),
        ("deleted", integer(counts.deleted)),
        ("deleted_archives", integer(counts.deleted_archives)),
        (
            "deleted_query_artifacts",
            integer(counts.deleted_query_artifacts),
        ),
        (
            "dropped_old_name_views",
            integer(counts.dropped_old_name_views),
        ),
        ("pruned_direct_state", integer(counts.pruned_direct_state)),
    ])
}

fn item_payload(item: &JanitorItemText) -> JsonValue {
    object(vec![
        ("phase", text(item.phase.value())),
        ("action", text(&item.action)),
        ("name", text(&item.name)),
        ("destination", optional_text(item.destination.as_deref())),
        (
            "status",
            text(if item.error.is_some() { "failed" } else { "ok" }),
        ),
        ("error", optional_text(item.error.as_deref())),
        (
            "duration_seconds",
            item.duration_seconds
                .map_or(JsonValue::Null, JsonValue::Float),
        ),
    ])
}

/// The counts, actions and duration of a run.
pub(crate) fn run_payload(run: &JanitorRunText) -> JsonValue {
    object(vec![
        ("counts", counts_payload(&run.counts)),
        ("elapsed_seconds", JsonValue::Float(run.elapsed_seconds)),
        (
            "items",
            JsonValue::Array(run.items.iter().map(item_payload).collect()),
        ),
    ])
}
