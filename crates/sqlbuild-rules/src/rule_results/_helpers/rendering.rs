//! A rules result as CLI text or as indented, key-sorted JSON.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

use crate::rule_results::constants::{FIX_AVAILABLE_NOTE, JSON_INDENT};
use crate::rule_results::models::{ResultCounts, RuleFinding};

pub(crate) fn result_text(findings: &[RuleFinding], counts: ResultCounts) -> String {
    if findings.is_empty() {
        return format!(
            "Rules passed: {} models evaluated, 0 findings ({} cache hits, {} misses)",
            counts.evaluated_models, counts.cache_hits, counts.cache_misses
        );
    }
    let mut blocks: Vec<String> = Vec::new();
    for finding in findings {
        blocks.push(format!(
            "{}:{}:{} [{}] {}\n  Remediation: {}",
            finding.path,
            finding.line,
            finding.column,
            finding.code,
            finding.message,
            finding.remediation
        ));
        if !finding.affected_rules.is_empty() {
            blocks.push(format!(
                "  Affected Rules: {}",
                finding.affected_rules.join(", ")
            ));
        }
        if finding.fixable {
            blocks.push(format!("  {FIX_AVAILABLE_NOTE}"));
        }
    }
    blocks.push(format!("Found {} Rules findings", findings.len()));
    if counts.unevaluated_resources != 0 {
        blocks.push(format!(
            "{} models evaluated, {} resources could not be evaluated",
            counts.evaluated_models, counts.unevaluated_resources
        ));
    }
    blocks.join("\n")
}

fn integer(value: i64) -> JsonValue {
    JsonInteger::parse(&value.to_string()).map_or(JsonValue::Null, JsonValue::Integer)
}

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn finding_json(finding: &RuleFinding) -> JsonValue {
    let mut entries: Vec<(String, JsonValue)> = vec![
        ("code".to_owned(), text(&finding.code)),
        ("path".to_owned(), text(&finding.path)),
        ("line".to_owned(), integer(finding.line)),
        ("column".to_owned(), integer(finding.column)),
        ("message".to_owned(), text(&finding.message)),
        ("remediation".to_owned(), text(&finding.remediation)),
    ];
    if !finding.affected_rules.is_empty() {
        entries.push((
            "affected_rules".to_owned(),
            JsonValue::Array(
                finding
                    .affected_rules
                    .iter()
                    .map(|rule| text(rule))
                    .collect(),
            ),
        ));
    }
    if finding.fixable {
        entries.push(("fixable".to_owned(), JsonValue::Bool(true)));
    }
    JsonValue::Object(entries)
}

pub(crate) fn result_json(findings: &[RuleFinding], counts: ResultCounts) -> String {
    let payload: JsonValue = JsonValue::Object(vec![
        (
            "evaluated_models".to_owned(),
            integer(counts.evaluated_models),
        ),
        (
            "unevaluated_resources".to_owned(),
            integer(counts.unevaluated_resources),
        ),
        ("cache_hits".to_owned(), integer(counts.cache_hits)),
        ("cache_misses".to_owned(), integer(counts.cache_misses)),
        (
            "finding_count".to_owned(),
            integer(i64::try_from(findings.len()).unwrap_or(i64::MAX)),
        ),
        (
            "findings".to_owned(),
            JsonValue::Array(findings.iter().map(finding_json).collect()),
        ),
    ]);
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(Some(JSON_INDENT))
    };
    dumps(&payload, &JsonDialect::Stdlib(options)).unwrap_or_default()
}
