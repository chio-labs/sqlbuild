//! Direct semantic uses resolved to SQLBuild resources and authored locations.

use std::collections::BTreeMap;

use serde_json::{Value, json};

use crate::lineage::_helpers::references::{
    normalized_sql, physical_resource_name, physical_resources,
};
use crate::lineage::models::{DirectSemanticUse, RichSchemaResource};

/// Keep resource precedence and model order identical to the compiler's lineage view.
pub(crate) fn direct_semantic_uses(
    schema: &[RichSchemaResource],
    models: &[(String, String, String)],
    dialect: &str,
) -> Result<Vec<DirectSemanticUse>, String> {
    let tables: Vec<Value> = schema_mapping(schema)
        .into_iter()
        .map(schema_table)
        .collect();
    model_uses(models, dialect, &tables)
}

/// Assigned columns override earlier values; declared defaults never override inference.
fn schema_mapping(schema: &[RichSchemaResource]) -> BTreeMap<String, BTreeMap<String, String>> {
    let mut tables: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    for resource in schema {
        let mut columns: BTreeMap<String, String> = BTreeMap::new();
        for (name, kind) in &resource.assigned {
            columns.insert(name.clone(), column_type(kind));
        }
        for (name, kind) in &resource.defaulted {
            columns
                .entry(name.clone())
                .or_insert_with(|| column_type(kind));
        }
        if !columns.is_empty() {
            tables.insert(
                physical_resource_name(resource.resource_type, &resource.name),
                columns,
            );
        }
    }
    tables
}

fn model_uses(
    models: &[(String, String, String)],
    dialect: &str,
    tables: &[Value],
) -> Result<Vec<DirectSemanticUse>, String> {
    let mut result: Vec<DirectSemanticUse> = Vec::new();
    for (model, query, authored) in models {
        let resources = physical_resources(query);
        let request = json!({
            "sql": normalized_sql(query), "dialect": dialect,
            "schema": {"strict": true, "tables": tables}
        });
        let response = crate::semantic_usage::main::analyze_json(&request.to_string())?;
        let response: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        let Some(uses) = response.get("uses").and_then(Value::as_array) else {
            return Err("native semantic usage analysis returned an invalid response".to_owned());
        };
        for usage in uses {
            let (Some(source), Some(column), Some(context), Some(expression)) = (
                usage.get("sourceName").and_then(Value::as_str),
                usage.get("column").and_then(Value::as_str),
                usage.get("context").and_then(Value::as_str),
                usage.get("expressionSql").and_then(Value::as_str),
            ) else {
                continue;
            };
            let Some(resource) = resources
                .iter()
                .rev()
                .find(|item| item.physical_name == source)
            else {
                continue;
            };
            let fallback = (
                usage.get("line").and_then(Value::as_u64),
                usage.get("columnOffset").and_then(Value::as_u64),
            );
            let (line, offset) = authored_position(authored, column).unwrap_or(fallback);
            result.push(DirectSemanticUse {
                model: model.clone(),
                context: context.to_owned(),
                expression: expression.to_owned(),
                resource_type: resource.resource_type,
                resource_name: resource.resource_name.clone(),
                column: column.to_owned(),
                confidence: usage
                    .get("confidence")
                    .and_then(Value::as_str)
                    .filter(|value| !value.is_empty())
                    .unwrap_or("unknown")
                    .to_owned(),
                line,
                offset,
            });
        }
    }
    Ok(result)
}

fn column_type(value: &Option<String>) -> String {
    value
        .as_deref()
        .filter(|value| !value.is_empty())
        .unwrap_or("UNKNOWN")
        .to_owned()
}

fn schema_table((name, columns): (String, BTreeMap<String, String>)) -> Value {
    let columns: Vec<Value> = columns
        .into_iter()
        .map(|(name, kind)| json!({"name": name, "type": kind}))
        .collect();
    json!({"name": name, "columns": columns})
}

fn authored_position(sql: &str, column: &str) -> Option<(Option<u64>, Option<u64>)> {
    let word = |value: char| value.is_ascii_alphanumeric() || value == '_';
    let mut next_allowed = 0;
    let mut matches = sql.char_indices().filter(|(start, _)| {
        if *start < next_allowed
            || !sql[*start..].starts_with(column)
            || sql[..*start].chars().next_back().is_some_and(word)
            || sql[*start + column.len()..]
                .chars()
                .next()
                .is_some_and(word)
        {
            return false;
        }
        next_allowed = *start + column.len();
        true
    });
    let (start, _) = matches.next()?;
    if matches.next().is_some() {
        return None;
    }
    let prefix = &sql[..start];
    let line = prefix.bytes().filter(|byte| *byte == b'\n').count() as u64 + 1;
    let offset = prefix
        .rsplit('\n')
        .next()
        .unwrap_or_default()
        .chars()
        .count() as u64
        + 1;
    Some((Some(line), Some(offset)))
}
