//! JSON documents of a cost run: the persisted artifact and the command output.

use crate::cost_report::constants::OUTPUT_SCHEMA_VERSION;
use crate::cost_report::models::{CostResource, CostRun, CostSummary};
use crate::json::models::{JsonInteger, JsonValue};

type Entries = Vec<(String, JsonValue)>;

fn string(text: &str) -> JsonValue {
    JsonValue::String(text.to_owned())
}

fn optional(text: Option<&String>) -> JsonValue {
    text.map_or(JsonValue::Null, |text| string(text))
}

fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}

fn object(entries: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        entries
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn strings(items: &[String]) -> JsonValue {
    JsonValue::Array(items.iter().map(|item| string(item)).collect())
}

fn optional_flag(flag: Option<bool>) -> JsonValue {
    flag.map_or(JsonValue::Null, JsonValue::Bool)
}

fn optional_integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, integer)
}

fn stored_resource(resource: &CostResource) -> JsonValue {
    object(vec![
        ("resource_type", string(&resource.resource_type)),
        ("resource_name", string(&resource.resource_name)),
        ("warehouse_name", string(&resource.warehouse_name)),
        ("warehouse_size", string(&resource.warehouse_size)),
        ("warehouse_type", optional(resource.warehouse_type.as_ref())),
        ("cluster_number", optional_integer(resource.cluster_number)),
        ("query_count", integer(resource.query_count)),
        ("attributed_seconds", string(&resource.attributed_seconds)),
        ("bytes_scanned", integer(resource.bytes_scanned)),
        (
            "estimated_compute_credits",
            string(&resource.estimated_compute_credits),
        ),
        ("estimated_usd", string(&resource.estimated_usd)),
    ])
}

fn stored_summary(cost: &CostSummary) -> JsonValue {
    object(vec![
        ("status", string(&cost.status)),
        ("usd_per_credit", string(&cost.usd_per_credit)),
        ("rate_source", string(&cost.rate_source)),
        (
            "resources",
            JsonValue::Array(cost.resources.iter().map(stored_resource).collect()),
        ),
        ("query_count", integer(cost.query_count)),
        ("attributed_seconds", string(&cost.attributed_seconds)),
        ("bytes_scanned", integer(cost.bytes_scanned)),
        (
            "estimated_compute_credits",
            string(&cost.estimated_compute_credits),
        ),
        ("estimated_usd", string(&cost.estimated_usd)),
        (
            "expected_statement_count",
            integer(cost.expected_statement_count),
        ),
        (
            "observed_statement_count",
            integer(cost.observed_statement_count),
        ),
        (
            "missing_statement_count",
            integer(cost.missing_statement_count),
        ),
        (
            "skipped_statement_count",
            integer(cost.skipped_statement_count),
        ),
        ("source", string(&cost.source)),
        ("method", string(&cost.method)),
        ("limitations", strings(&cost.limitations)),
        ("message", optional(cost.message.as_ref())),
    ])
}

/// `asdict(record)` with decimals and timestamps as text, as the artifact stores it.
pub(crate) fn artifact(run: &CostRun) -> JsonValue {
    object(vec![
        ("run_id", string(&run.run_id)),
        ("adapter_name", string(&run.adapter_name)),
        ("target_name", optional(run.target_name.as_ref())),
        ("build_status", string(&run.build_status)),
        ("started_at", string(&run.started_at)),
        ("completed_at", string(&run.completed_at)),
        ("cost", stored_summary(&run.cost)),
        ("version", integer(run.version)),
        (
            "had_executable_work",
            optional_flag(run.had_executable_work),
        ),
    ])
}

fn output_resource(resource: &CostResource) -> JsonValue {
    object(vec![
        ("resource_type", string(&resource.resource_type)),
        ("model", string(&resource.resource_name)),
        ("warehouse", string(&resource.warehouse_name)),
        ("warehouse_size", string(&resource.warehouse_size)),
        ("warehouse_type", optional(resource.warehouse_type.as_ref())),
        ("cluster_number", optional_integer(resource.cluster_number)),
        ("query_count", integer(resource.query_count)),
        ("attributed_seconds", string(&resource.attributed_seconds)),
        ("bytes_scanned", integer(resource.bytes_scanned)),
        (
            "attributed_compute_credits",
            string(&resource.estimated_compute_credits),
        ),
        ("estimated_usd", string(&resource.estimated_usd)),
    ])
}

fn coverage(cost: &CostSummary) -> JsonValue {
    object(vec![
        ("query_count", integer(cost.query_count)),
        (
            "model_rows",
            integer(i64::try_from(cost.resources.len()).unwrap_or(i64::MAX)),
        ),
        (
            "expected_statement_count",
            integer(cost.expected_statement_count),
        ),
        (
            "observed_statement_count",
            integer(cost.observed_statement_count),
        ),
        (
            "missing_statement_count",
            integer(cost.missing_statement_count),
        ),
        (
            "skipped_statement_count",
            integer(cost.skipped_statement_count),
        ),
    ])
}

fn totals(cost: &CostSummary) -> JsonValue {
    object(vec![
        ("query_count", integer(cost.query_count)),
        ("attributed_seconds", string(&cost.attributed_seconds)),
        ("bytes_scanned", integer(cost.bytes_scanned)),
        (
            "attributed_compute_credits",
            string(&cost.estimated_compute_credits),
        ),
        ("estimated_usd", string(&cost.estimated_usd)),
    ])
}

/// `cost_output_payload`: the `sqb cost --json` document of one run.
pub(crate) fn output(run: &CostRun) -> JsonValue {
    let cost: &CostSummary = &run.cost;
    let entries: Entries = vec![
        ("schema_version".to_owned(), integer(OUTPUT_SCHEMA_VERSION)),
        ("command".to_owned(), string("cost")),
        ("run_id".to_owned(), string(&run.run_id)),
        ("build_status".to_owned(), string(&run.build_status)),
        ("started_at".to_owned(), string(&run.started_at)),
        ("completed_at".to_owned(), string(&run.completed_at)),
        ("adapter".to_owned(), string(&run.adapter_name)),
        ("target".to_owned(), optional(run.target_name.as_ref())),
        (
            "had_executable_work".to_owned(),
            optional_flag(run.had_executable_work),
        ),
        ("status".to_owned(), string(&cost.status)),
        ("source".to_owned(), string(&cost.source)),
        ("currency".to_owned(), string("USD")),
        ("usd_per_credit".to_owned(), string(&cost.usd_per_credit)),
        ("rate_source".to_owned(), string(&cost.rate_source)),
        ("method".to_owned(), string(&cost.method)),
        ("limitations".to_owned(), strings(&cost.limitations)),
        ("message".to_owned(), optional(cost.message.as_ref())),
        ("coverage".to_owned(), coverage(cost)),
        (
            "per_model".to_owned(),
            JsonValue::Array(cost.resources.iter().map(output_resource).collect()),
        ),
        ("totals".to_owned(), totals(cost)),
    ];
    JsonValue::Object(entries)
}

/// `format_cost_history_json`'s document of several runs.
pub(crate) fn history(runs: &[CostRun], matching_count: Option<usize>) -> JsonValue {
    let count: i64 = i64::try_from(runs.len()).unwrap_or(i64::MAX);
    let matching: i64 = matching_count.map_or(count, |matching| {
        i64::try_from(matching).unwrap_or(i64::MAX)
    });
    object(vec![
        ("schema_version", integer(OUTPUT_SCHEMA_VERSION)),
        ("command", string("cost_history")),
        ("count", integer(count)),
        ("matching_count", integer(matching)),
        ("runs", JsonValue::Array(runs.iter().map(output).collect())),
    ])
}
