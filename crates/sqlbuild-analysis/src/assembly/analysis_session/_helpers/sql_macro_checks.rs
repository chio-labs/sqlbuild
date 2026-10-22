//! A model's SQL macro call arguments checked against the column types its analysed SQL shows.

use serde_json::{Value, json};

use crate::assembly::analysis_session::types::Shapes;
use crate::query_analysis::main::analyze::analyze_json;
use crate::sql_macros::main::sql_macro_findings::sql_macro_findings;
use crate::sql_macros::main::sql_macro_probes::sql_macro_probes;
use crate::sql_macros::models::{SqlMacroCheck, SqlMacroFinding};

/// A probe's `(column, type)` list, or `None` where its analysis did not know every column.
type ProbeColumns = Option<Vec<(String, Option<String>)>>;

/// The findings of `checks` against the analysed SQL `cleaned_sql` and its bound relations.
pub(crate) fn checked_sql_macros(
    dialect: &str,
    (cleaned_sql, schema): (&str, &Shapes),
    checks: &[SqlMacroCheck],
) -> Vec<SqlMacroFinding> {
    let plan = sql_macro_probes(cleaned_sql, checks);
    if plan.probes.is_empty() {
        return Vec::new();
    }
    let tables: Vec<Value> = schema
        .iter()
        .map(|(name, columns)| table(name, columns))
        .collect();
    let requests: Vec<Value> = plan
        .probes
        .iter()
        .map(|sql| json!({"sql": sql, "dialect": dialect, "schema": {"tables": tables}}))
        .collect();
    let Ok(response) = analyze_json(&json!({ "requests": requests }).to_string()) else {
        return Vec::new();
    };
    let Ok(Value::Array(analyses)) = serde_json::from_str::<Value>(&response) else {
        return Vec::new();
    };
    let results: Vec<ProbeColumns> = analyses.iter().map(probe_columns).collect();
    sql_macro_findings((&plan, checks), &results, dialect)
}

/// One bound relation as a validation schema table, its qualified name split into parts.
fn table(name: &str, columns: &[(String, String)]) -> Value {
    let mut parts: Vec<&str> = name.split('.').collect();
    let table_name: &str = parts.pop().unwrap_or(name);
    let columns: Vec<Value> = columns
        .iter()
        .map(|(column, data_type)| json!({"name": column, "type": data_type}))
        .collect();
    let mut entry: Value = json!({"name": table_name, "columns": columns});
    if let Some(schema) = parts.pop() {
        entry["schema"] = json!(schema);
    }
    if let Some(catalog) = parts.pop() {
        entry["catalog"] = json!(catalog);
    }
    entry
}

/// A probe analysis's output columns, unless it failed or left a star unresolved.
fn probe_columns(analysis: &Value) -> ProbeColumns {
    let projections: &Vec<Value> = analysis.pointer("/analysis/projections")?.as_array()?;
    projections
        .iter()
        .map(|projection| {
            let name: &str = projection.get("name")?.as_str()?;
            if projection.get("isStar").and_then(Value::as_bool) == Some(true) || name == "*" {
                return None;
            }
            let data_type: Option<String> = projection
                .get("typeHint")
                .and_then(Value::as_str)
                .filter(|hint| !hint.eq_ignore_ascii_case("UNKNOWN"))
                .map(str::to_owned);
            Some((name.to_owned(), data_type))
        })
        .collect()
}
