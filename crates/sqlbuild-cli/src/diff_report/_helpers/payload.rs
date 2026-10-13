//! The structured JSON diff document, before serialization.

use sqlbuild_core::json::models::{JsonInteger, JsonValue};

use crate::diff_report::_helpers::evidence::render_example_pair;
use crate::diff_report::_helpers::findings::resolved_outcome;
use crate::diff_report::constants::{FINDINGS_OUTCOME, PASS_OUTCOME, QUERY_INPUT_KIND};
use crate::diff_report::models::{
    DiffCoverageFacts, DiffDocumentOptions, DiffExampleOptions, DiffModelFacts, DiffValue,
    RenderedValue,
};
use crate::diff_report::types::DiffNamedValue;

pub(crate) fn integer(value: i64) -> JsonValue {
    JsonInteger::parse(&value.to_string()).map_or(JsonValue::Null, JsonValue::Integer)
}

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn object(entries: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        entries
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn strings(values: &[String]) -> JsonValue {
    JsonValue::Array(values.iter().map(|value| text(value)).collect())
}

fn optional(value: Option<&DiffValue>) -> JsonValue {
    value.map_or(JsonValue::Null, |value| value.json.clone())
}

/// `{name: value}` where a repeated name keeps its first position and last value.
fn named_values(values: &[DiffNamedValue]) -> JsonValue {
    let mut entries: Vec<(String, JsonValue)> = Vec::new();
    for (name, value) in values {
        match entries.iter_mut().find(|(existing, _)| existing == name) {
            Some(entry) => entry.1 = value.json.clone(),
            None => entries.push((name.clone(), value.json.clone())),
        }
    }
    JsonValue::Object(entries)
}

fn rendered(value: &RenderedValue) -> JsonValue {
    object(vec![
        ("value", value.text.as_deref().map_or(JsonValue::Null, text)),
        ("original_length", integer(value.original_length as i64)),
        ("truncated", JsonValue::Bool(value.truncated)),
        ("suppressed", JsonValue::Bool(value.suppressed)),
        (
            "first_difference",
            value
                .first_difference
                .map_or(JsonValue::Null, |index| integer(index as i64)),
        ),
    ])
}

fn coverage(coverage: Option<&DiffCoverageFacts>) -> JsonValue {
    coverage.map_or(JsonValue::Null, |coverage| {
        object(vec![
            ("row_count", integer(coverage.row_count)),
            ("minimum_cursor", optional(coverage.minimum_cursor.as_ref())),
            ("maximum_cursor", optional(coverage.maximum_cursor.as_ref())),
        ])
    })
}

fn examples(model: &DiffModelFacts, options: DiffExampleOptions) -> JsonValue {
    let mut values_truncated: bool = false;
    let mut unequal_rows: Vec<JsonValue> = Vec::new();
    for sample in &model.unequal_samples {
        let mut cells: Vec<JsonValue> = Vec::new();
        for cell in &sample.changed_cells {
            let (left, right) = render_example_pair(&cell.left.text, &cell.right.text, options);
            values_truncated = values_truncated || left.truncated || right.truncated;
            cells.push(object(vec![
                ("column", text(&cell.name)),
                ("from", rendered(&left)),
                ("to", rendered(&right)),
            ]));
        }
        unequal_rows.push(object(vec![
            ("key", named_values(&sample.key_values)),
            ("changed_cells", JsonValue::Array(cells)),
        ]));
    }
    let truncated_by_count: bool = model.rows.as_ref().is_some_and(|rows| {
        rows.unequal_count > model.unequal_samples.len() as i64
            || rows.left_only_count > model.left_only_keys.len() as i64
            || rows.right_only_count > model.right_only_keys.len() as i64
    });
    let keys = |samples: &[Vec<DiffNamedValue>]| {
        JsonValue::Array(samples.iter().map(|sample| named_values(sample)).collect())
    };
    object(vec![
        ("unequal_rows", JsonValue::Array(unequal_rows)),
        ("from_only_keys", keys(&model.left_only_keys)),
        ("to_only_keys", keys(&model.right_only_keys)),
        ("truncated_by_count", JsonValue::Bool(truncated_by_count)),
        ("values_truncated", JsonValue::Bool(values_truncated)),
        (
            "values_suppressed",
            JsonValue::Bool(options.suppress_values),
        ),
        (
            "max_value_length",
            options
                .max_value_length
                .map_or(JsonValue::Null, |limit| integer(limit as i64)),
        ),
    ])
}

fn model_payload(model: &DiffModelFacts, options: &DiffDocumentOptions) -> JsonValue {
    let type_changes: Vec<JsonValue> = model
        .type_changes
        .iter()
        .map(|(name, from_type, to_type)| {
            object(vec![
                ("name", text(name)),
                ("from_type", text(from_type)),
                ("to_type", text(to_type)),
            ])
        })
        .collect();
    let mut entries: Vec<(&str, JsonValue)> = vec![
        ("input_kind", text(&model.input_kind)),
        ("name", text(&model.name)),
        ("from_label", text(&options.from_label)),
        ("to_label", text(&options.to_label)),
        ("from_relation", text(&model.left_relation)),
        ("to_relation", text(&model.right_relation)),
        ("unique_key", strings(&model.unique_key)),
        ("unkeyed", JsonValue::Bool(model.unkeyed)),
        ("excluded_columns", strings(&model.excluded_columns)),
        (
            "schema",
            object(vec![
                ("added_columns", strings(&model.added_columns)),
                ("removed_columns", strings(&model.removed_columns)),
                ("type_changed_columns", JsonValue::Array(type_changes)),
            ]),
        ),
    ];
    let Some(rows) = &model.rows else {
        entries.push(("comparison_scope", text("schema_only")));
        return object(entries);
    };
    let keyed = |value: i64| {
        if model.unkeyed {
            JsonValue::Null
        } else {
            integer(value)
        }
    };
    let changed: Vec<(String, JsonValue)> = rows
        .columns
        .iter()
        .map(|column| (column.name.clone(), integer(column.mismatched_count)))
        .collect();
    let mismatches: Vec<JsonValue> = rows
        .columns
        .iter()
        .filter(|column| column.mismatched_count > 0)
        .map(|column| {
            object(vec![
                ("column", text(&column.name)),
                ("rows", integer(column.mismatched_count)),
            ])
        })
        .collect();
    entries.extend([
        (
            "comparison_scope",
            text(if rows.exhaustive {
                "exhaustive"
            } else {
                "sampled"
            }),
        ),
        (
            "coverage",
            object(vec![
                (
                    "requested",
                    object(vec![
                        (
                            "cursor_column",
                            rows.cursor_column.as_deref().map_or(JsonValue::Null, text),
                        ),
                        ("start", optional(rows.cursor_start.as_ref())),
                        ("end", optional(rows.cursor_end.as_ref())),
                    ]),
                ),
                ("from", coverage(rows.left_coverage.as_ref())),
                ("to", coverage(rows.right_coverage.as_ref())),
                (
                    "differs",
                    JsonValue::Bool(rows.cursor_column.is_some() && rows.coverage_differs),
                ),
            ]),
        ),
        (
            "sampling",
            object(vec![
                (
                    "configured_row_limit",
                    rows.sampling
                        .map_or(JsonValue::Null, |(limit, _)| integer(limit)),
                ),
                (
                    "seed",
                    rows.sampling
                        .map_or(JsonValue::Null, |(_, seed)| integer(seed)),
                ),
                ("population_keys", keyed(rows.population_count)),
                ("compared_keys", keyed(rows.compared_count)),
                (
                    "coverage_ratio",
                    JsonValue::Float(if rows.population_count == 0 {
                        1.0
                    } else {
                        rows.compared_count as f64 / rows.population_count as f64
                    }),
                ),
                ("exhaustive", JsonValue::Bool(rows.exhaustive)),
            ]),
        ),
        (
            "rows",
            object(vec![
                ("from_count", integer(rows.left_count)),
                ("to_count", integer(rows.right_count)),
                (
                    "joined_count",
                    integer(rows.equal_count + rows.unequal_count),
                ),
                ("equal_count", integer(rows.equal_count)),
                ("unequal_count", integer(rows.unequal_count)),
                ("from_only_count", integer(rows.left_only_count)),
                ("to_only_count", integer(rows.right_only_count)),
                ("changed_columns", JsonValue::Object(unique(changed))),
                ("column_mismatches", JsonValue::Array(mismatches)),
            ]),
        ),
        ("examples", examples(model, options.examples)),
    ]);
    object(entries)
}

fn unique(entries: Vec<(String, JsonValue)>) -> Vec<(String, JsonValue)> {
    let mut result: Vec<(String, JsonValue)> = Vec::new();
    for (key, value) in entries {
        match result.iter_mut().find(|(existing, _)| *existing == key) {
            Some(entry) => entry.1 = value,
            None => result.push((key, value)),
        }
    }
    result
}

/// Python's `round(value, 6)`.
fn round_six(value: f64) -> f64 {
    format!("{value:.6}").parse::<f64>().unwrap_or(value)
}

/// The complete diff document.
pub(crate) fn document(models: &[DiffModelFacts], options: &DiffDocumentOptions) -> JsonValue {
    let payloads: Vec<JsonValue> = models
        .iter()
        .map(|model| model_payload(model, options))
        .collect();
    let outcome: String = resolved_outcome(models, options.outcome.as_deref());
    let status: &str = match outcome.as_str() {
        PASS_OUTCOME => "no_differences_found",
        FINDINGS_OUTCOME => "differences_found",
        other => other,
    };
    let query_payloads: Vec<JsonValue> = models
        .iter()
        .zip(&payloads)
        .filter(|(model, _)| model.input_kind == QUERY_INPUT_KIND)
        .map(|(_, payload)| payload.clone())
        .collect();
    let mut entries: Vec<(&str, JsonValue)> = vec![
        ("schema_version", integer(1)),
        ("status", text(status)),
        ("outcome", text(&outcome)),
        ("from", text(&options.from_label)),
        ("to", text(&options.to_label)),
        ("models", JsonValue::Array(payloads)),
    ];
    if !query_payloads.is_empty() {
        entries.push(("input_kind", text(QUERY_INPUT_KIND)));
        entries.push(("query_comparisons", JsonValue::Array(query_payloads)));
    }
    if let Some(phases) = &options.phase_seconds {
        let mut sorted: Vec<(String, f64)> = phases.clone();
        sorted.sort_by(|a, b| a.0.cmp(&b.0));
        entries.push((
            "phase_seconds",
            JsonValue::Object(
                sorted
                    .into_iter()
                    .map(|(phase, seconds)| (phase, JsonValue::Float(round_six(seconds))))
                    .collect(),
            ),
        ));
    }
    json_safe(object(entries))
}

/// Non-finite floats as `{"kind": "non_finite_number", "value": ...}` objects.
fn json_safe(value: JsonValue) -> JsonValue {
    match value {
        JsonValue::Float(number) if !number.is_finite() => {
            let label: &str = if number.is_nan() {
                "NaN"
            } else if number.is_sign_positive() {
                "Infinity"
            } else {
                "-Infinity"
            };
            object(vec![
                ("kind", text("non_finite_number")),
                ("value", text(label)),
            ])
        }
        JsonValue::Array(items) => JsonValue::Array(items.into_iter().map(json_safe).collect()),
        JsonValue::Object(entries) => JsonValue::Object(
            entries
                .into_iter()
                .map(|(key, item)| (key, json_safe(item)))
                .collect(),
        ),
        other => other,
    }
}
