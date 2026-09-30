use crate::column_references::main::analyze::analyze_json;
use serde_json::{Value, json};

pub(crate) fn analyze(sql: &str, output_ctes: &[&str]) -> Result<Value, String> {
    let request: Value = json!({
        "sql": sql,
        "dialect": "duckdb",
        "column": "amount",
        "schema": {"strict": false, "tables": [
            {"name": "orders_fact", "columns": [
                {"name": "order_id", "type": "INTEGER"},
                {"name": "amount", "type": "INTEGER"}
            ]},
            {"name": "customers", "columns": [
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "order_id", "type": "INTEGER"}
            ]}
        ]},
        "target_tables": ["orders_fact"],
        "output_ctes": output_ctes,
    });
    serde_json::from_str(&analyze_json(&request.to_string())?).map_err(|error| error.to_string())
}

pub(crate) fn slices(sql: &str, sites: &Value, start: &str, end: &str) -> Vec<String> {
    let chars: Vec<char> = sql.chars().collect();
    sites
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| span_text(&chars, item, start, end))
                .collect()
        })
        .unwrap_or_default()
}

pub(crate) fn strings(sites: &Value, key: &str) -> Vec<String> {
    sites
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item[key].as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

pub(crate) fn count(sites: &Value) -> usize {
    sites.as_array().map_or(0, Vec::len)
}

fn span_text(chars: &[char], item: &Value, start: &str, end: &str) -> Option<String> {
    let start: usize = usize::try_from(item[start].as_u64()?).ok()?;
    let end: usize = usize::try_from(item[end].as_u64()?).ok()?;
    Some(chars[start..end].iter().collect())
}
