//! `sqb rules list` text: one `code  message` line per rule, or the sorted JSON document.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::rule_catalogue::models::RuleListing;

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn rule_object(rule: &RuleListing) -> JsonValue {
    JsonValue::Object(vec![
        ("code".to_owned(), text(&rule.code)),
        ("family".to_owned(), text(&rule.family)),
        ("message".to_owned(), text(&rule.message)),
        ("custom".to_owned(), JsonValue::Bool(rule.custom)),
        (
            "subject".to_owned(),
            rule.subject.as_deref().map_or(JsonValue::Null, text),
        ),
    ])
}

/// The listing without its trailing newline: `json.dumps({"rules": ...}, sort_keys=True)` or lines.
#[must_use]
pub fn render_rule_list(rules: &[RuleListing], json_output: bool) -> String {
    if !json_output {
        return rules
            .iter()
            .map(|rule| format!("{}  {}", rule.code, rule.message))
            .collect::<Vec<String>>()
            .join("\n");
    }
    let payload: JsonValue = JsonValue::Object(vec![(
        "rules".to_owned(),
        JsonValue::Array(rules.iter().map(rule_object).collect()),
    )]);
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None)
    };
    dumps(&payload, &JsonDialect::Stdlib(options)).unwrap_or_default()
}
