//! Format report entries as JSON values.

use crate::format_command::constants::{SEVERITY_FAULT, SEVERITY_WARNING};
use crate::format_command::models::{LintFinding, RuleFixLine};
use crate::json::models::{JsonInteger, JsonValue};

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}

fn optional_integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, integer)
}

pub(crate) fn count(value: usize) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value as u64))
}

pub(crate) fn fix_object(fix: &RuleFixLine) -> JsonValue {
    JsonValue::Object(vec![
        ("file".to_owned(), text(&fix.file)),
        ("code".to_owned(), text(&fix.code)),
        ("line".to_owned(), integer(fix.line)),
        ("status".to_owned(), text(&fix.status)),
        ("reason".to_owned(), text(&fix.reason)),
    ])
}

pub(crate) fn finding_object(finding: &LintFinding) -> JsonValue {
    let severity: &str = if finding.fault {
        SEVERITY_FAULT
    } else {
        SEVERITY_WARNING
    };
    JsonValue::Object(vec![
        ("code".to_owned(), text(&finding.code)),
        ("column".to_owned(), integer(finding.column)),
        (
            "end_column".to_owned(),
            optional_integer(finding.end_column),
        ),
        ("end_line".to_owned(), optional_integer(finding.end_line)),
        ("engine".to_owned(), text(&finding.engine)),
        ("file".to_owned(), text(&finding.file)),
        ("line".to_owned(), integer(finding.line)),
        ("message".to_owned(), text(&finding.message)),
        (
            "remediation".to_owned(),
            finding.remediation.as_deref().map_or(JsonValue::Null, text),
        ),
        ("severity".to_owned(), text(severity)),
    ])
}
