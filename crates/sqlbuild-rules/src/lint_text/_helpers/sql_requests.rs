//! Native SQL lint request payloads and the batch engine call.

use std::borrow::Cow;

use serde_json::{Map, Value};
use sqlbuild_attachments::ceremonial_select::main::omitted_select_offset::omitted_select_offset;
use sqlbuild_attachments::ceremonial_select::models::OmittedSelect;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::lint_text::_helpers::sql_diagnostics::without_generated_comments;
use crate::lint_text::constants::{
    CROSS_KEYWORD, INVALID_BATCH, LINE_COMMENT_PREFIX, LINT_API_VERSION,
    OMITTED_CEREMONIAL_SELECT_SQL,
};
use crate::lint_text::models::{LintSqlBody, LintSqlOptions};
use crate::sql_lint::main::batch_engine::lint_batch_json;

/// Where a fixture body omits its ceremonial `SELECT 1`, so the parser sees one statement.
pub(crate) fn omitted_select(body: &LintSqlBody) -> Option<usize> {
    if !body.allows_ceremonial_select {
        return None;
    }
    let syntax: LexicalSyntax = LexicalSyntax {
        line_comment_prefixes: vec![LINE_COMMENT_PREFIX.to_string()],
        ..LexicalSyntax::default()
    };
    match omitted_select_offset(&body.lint_text, &syntax) {
        OmittedSelect::At(offset) => Some(offset),
        OmittedSelect::Absent => None,
    }
}

/// Whether `text` may hold a `CROSS JOIN`; other bodies omit relation names to share requests.
fn mentions_cross_join(text: &str) -> bool {
    text.as_bytes()
        .windows(CROSS_KEYWORD.len())
        .any(|window| window.eq_ignore_ascii_case(CROSS_KEYWORD))
}

fn strings(values: &[String]) -> Value {
    Value::from(values.to_vec())
}

/// The engine request for one body, with the omitted `SELECT 1` added back.
pub(crate) fn lint_payload(
    (body, file): (&LintSqlBody, &str),
    omitted: Option<usize>,
    options: &LintSqlOptions,
) -> Value {
    let lint_text: Cow<'_, str> = without_generated_comments(body, (file, &options.dialect));
    let sql: String = match omitted {
        Some(offset) => {
            let characters: Vec<char> = lint_text.chars().collect();
            let head: String = characters[..offset].iter().collect();
            let tail: String = characters[offset..].iter().collect();
            format!("{head}{OMITTED_CEREMONIAL_SELECT_SQL}{tail}")
        }
        None => lint_text.into_owned(),
    };
    let mut payload: Map<String, Value> = Map::new();
    let _ = payload.insert("version".to_string(), Value::from(LINT_API_VERSION));
    let _ = payload.insert("sql".to_string(), Value::from(sql));
    let _ = payload.insert("dialect".to_string(), Value::from(options.dialect.clone()));
    if let Some(enabled) = &options.enabled_rules {
        let _ = payload.insert("enabled_rules".to_string(), strings(enabled));
    }
    let lists: [(&str, &[String]); 4] = [
        ("ignored_rules", &options.ignored_rules),
        ("external_identifiers", &body.external_identifiers),
        ("dependency_identifiers", &body.dependency_identifiers),
        (
            "externally_referenced_ctes",
            &body.externally_referenced_ctes,
        ),
    ];
    for (key, values) in lists {
        if !values.is_empty() {
            let _ = payload.insert(key.to_string(), strings(values));
        }
    }
    let flags: [(&str, bool); 3] = [
        ("allows_ceremonial_select", body.allows_ceremonial_select),
        (
            "allows_dynamic_output_star",
            body.allows_dynamic_output_star,
        ),
        ("allows_empty_fixture_star", body.allows_empty_fixture_star),
    ];
    for (key, enabled) in flags {
        if enabled {
            let _ = payload.insert(key.to_string(), Value::Bool(true));
        }
    }
    let _ = payload.insert(
        "max_literal_length".to_string(),
        Value::from(options.max_literal_length),
    );
    let _ = payload.insert(
        "max_ranking_order_by".to_string(),
        Value::from(options.max_ranking_order_by),
    );
    if !body.relation_keys.is_empty() {
        let keys: Map<String, Value> = body
            .relation_keys
            .iter()
            .map(|(sentinel, keys)| (sentinel.clone(), Value::from(keys.clone())))
            .collect();
        let _ = payload.insert("relation_keys".to_string(), Value::Object(keys));
    }
    if !body.relation_names.is_empty() && mentions_cross_join(&body.lint_text) {
        let names: Map<String, Value> = body
            .relation_names
            .iter()
            .map(|(sentinel, name)| (sentinel.clone(), Value::from(name.clone())))
            .collect();
        let _ = payload.insert("relation_names".to_string(), Value::Object(names));
    }
    Value::Object(payload)
}

/// Run every payload through the batch engine, one response per payload.
pub(crate) fn run_batch(payloads: &[Value]) -> Result<Vec<Value>, String> {
    if payloads.is_empty() {
        return Ok(Vec::new());
    }
    let response: String = lint_batch_json(&Value::from(payloads.to_vec()).to_string())?;
    match serde_json::from_str::<Value>(&response).map_err(|error| error.to_string())? {
        Value::Array(responses) if responses.len() == payloads.len() => Ok(responses),
        _ => Err(INVALID_BATCH.to_string()),
    }
}
