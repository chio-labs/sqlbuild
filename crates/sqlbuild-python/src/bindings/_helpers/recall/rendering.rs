//! `sqb recall query` and `schema` output: text cells, CSV and the JSON document.

use serde_json::{Map, Value, json};
use sqlbuild_core::query_command::main::render_query_csv::render_query_csv;
use sqlbuild_core::query_command::main::render_query_long::render_query_long;
use sqlbuild_core::query_command::main::render_query_table::render_query_table;
use sqlbuild_core::query_command::models::QueryDisplay;
use sqlbuild_recall::records::models::RecallValue;
use sqlbuild_recall::schema::models::Dialect;
use sqlbuild_recall::store::models::{DescribedColumn, DescribedRelation, QueryResult};

use crate::bindings::_helpers::recall::clickhouse_calls::QueryStatistics;
use crate::bindings::_helpers::recall::constants::{
    BASE64_ALPHABET, CSV_FORMAT, JOIN_KEYS, JSON_FORMAT, TABLE_FORMAT,
};

fn base64(data: &[u8]) -> String {
    let mut encoded = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let bytes = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let triple = u32::from(bytes[0]) << 16 | u32::from(bytes[1]) << 8 | u32::from(bytes[2]);
        for index in 0..4 {
            if index <= chunk.len() {
                encoded.push(char::from(
                    BASE64_ALPHABET[(triple >> (18 - 6 * index) & 63) as usize],
                ));
            } else {
                encoded.push('=');
            }
        }
    }
    encoded
}

fn truncated(text: &str, max_bytes: Option<usize>) -> String {
    let Some(limit) = max_bytes.filter(|limit| text.len() > *limit) else {
        return text.to_owned();
    };
    let mut end = limit;
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}…[+{} bytes]", &text[..end], text.len() - end)
}

/// A cell as text formats show it; `null` is the text for SQL NULL.
pub(crate) fn display_cell(value: &RecallValue, null: &str, max_bytes: Option<usize>) -> String {
    match value {
        RecallValue::Null => null.to_owned(),
        RecallValue::Integer(number) => number.to_string(),
        RecallValue::Real(number) => format!("{number:?}"),
        RecallValue::Text(text) => truncated(text, max_bytes),
        RecallValue::Blob(data) => match std::str::from_utf8(data) {
            Ok(text) => truncated(text, max_bytes),
            Err(_) => format!("<{} bytes of binary data>", data.len()),
        },
    }
}

fn display_row(row: &[RecallValue], null: &str, max_bytes: Option<usize>) -> Vec<String> {
    let mut cells: Vec<String> = Vec::with_capacity(row.len());
    for value in row {
        cells.push(display_cell(value, null, max_bytes));
    }
    cells
}

fn column_json(column: &DescribedColumn) -> Value {
    json!({
        "name": column.name,
        "type": column.declared_type,
        "nullable": column.nullable,
    })
}

fn json_cell(value: &RecallValue) -> Value {
    match value {
        RecallValue::Null => Value::Null,
        RecallValue::Integer(number) => json!(number),
        RecallValue::Real(number) => json!(number),
        RecallValue::Text(text) => json!(text),
        RecallValue::Blob(data) => match std::str::from_utf8(data) {
            Ok(text) => json!(text),
            Err(_) => json!({ "base64": base64(data) }),
        },
    }
}

/// What the JSON document reports besides rows.
pub(crate) struct QueryContext<'a> {
    pub(crate) target: Option<&'a str>,
    /// The SQLite file or the ClickHouse database.
    pub(crate) store_path: &'a str,
    pub(crate) adapter: &'a str,
    pub(crate) limit: Option<usize>,
    pub(crate) elapsed_ms: f64,
    /// Server statistics; ClickHouse only.
    pub(crate) statistics: Option<&'a QueryStatistics>,
}

/// The rendered result in `format`: `long`, `table`, `csv` or `json`.
pub(crate) fn render_result(
    result: &QueryResult,
    format: &str,
    max_bytes: Option<usize>,
    context: &QueryContext<'_>,
) -> String {
    if format == JSON_FORMAT {
        let rows: Vec<Value> = result
            .rows
            .iter()
            .map(|row| Value::Array(row.iter().map(json_cell).collect()))
            .collect();
        let document = json!({
            "backend": "logs",
            "target": context.target,
            "store": {"adapter": context.adapter, "database": context.store_path},
            "columns": result.columns,
            "rows": rows,
            "row_count": result.rows.len(),
            "truncated": result.truncated,
            "limit": context.limit,
            "statistics": {
                "elapsed_ms": context.elapsed_ms,
                "rows_read": context.statistics.and_then(|statistics| statistics.rows_read),
                "bytes_read": context.statistics.and_then(|statistics| statistics.bytes_read),
                "query_id": context.statistics.and_then(|statistics| statistics.query_id.clone()),
            },
        });
        return format!("{document}\n");
    }
    let csv: bool = format == CSV_FORMAT;
    let null: &str = if csv { "" } else { "NULL" };
    let cells: Vec<Vec<String>> = result
        .rows
        .iter()
        .map(|row| display_row(row, null, max_bytes))
        .collect();
    if csv {
        return render_query_csv(&result.columns, &cells);
    }
    let display = QueryDisplay {
        columns: result.columns.clone(),
        rows: cells,
        truncated: result.truncated,
        limit: context
            .limit
            .map(|limit| i64::try_from(limit).unwrap_or(i64::MAX)),
    };
    if format == TABLE_FORMAT {
        render_query_table(&display)
    } else {
        render_query_long(&display)
    }
}

fn relation_note(name: &str) -> &'static str {
    match name {
        "invocations" => {
            "one row per invocation; status is completed, failed, running, abandoned or unknown"
        }
        "statements" => "one row per statement; outcome no_terminal means no terminal fact arrived",
        "audit_results" => "one row per evaluated audit",
        "output_invocations" => {
            "output completeness per invocation: gaps, drops, filtering, truncation, flush"
        }
        "output_tail" => "the last 200 output chunks of each invocation as text",
        "output_transcripts" => "exact stdout, stderr and combined bytes per invocation",
        "events" => "every lifecycle fact",
        "diagnostics" => "structured diagnostics at or above the configured severity",
        "artifacts" => "captured SQL and other artifacts, by reference",
        "conflicts" => "record keys reused with different content; the first row is kept",
        _ => "",
    }
}

/// The schema document: relations with columns, join keys and time semantics.
pub(crate) fn render_schema(
    relations: &[DescribedRelation],
    json_output: bool,
    (store_path, store_dialect, retention_days): (&str, Dialect, u32),
) -> String {
    let (adapter, dialect, time_semantics): (&str, &str, &str) = match store_dialect {
        Dialect::ClickHouse => (
            "clickhouse",
            "ClickHouse",
            "timestamps are DateTime64(6, 'UTC')",
        ),
        Dialect::Sqlite => (
            "sqlite",
            "SQLite",
            "timestamps are ISO-8601 UTC text with microseconds",
        ),
    };
    let filter_hint =
        "filter invocation_started_at to bound scans; all rows of an invocation expire together";
    if json_output {
        let items: Vec<Value> = relations
            .iter()
            .map(|relation| {
                let mut item = Map::new();
                item.insert("name".to_owned(), json!(relation.name));
                item.insert("kind".to_owned(), json!(relation.kind));
                item.insert(
                    "description".to_owned(),
                    json!(relation_note(&relation.name)),
                );
                item.insert(
                    "join_keys".to_owned(),
                    json!(
                        relation
                            .columns
                            .iter()
                            .filter(|column| JOIN_KEYS.contains(&column.name.as_str()))
                            .map(|column| column.name.clone())
                            .collect::<Vec<_>>()
                    ),
                );
                item.insert(
                    "columns".to_owned(),
                    Value::Array(relation.columns.iter().map(column_json).collect()),
                );
                Value::Object(item)
            })
            .collect();
        let document = json!({
            "backend": "logs",
            "dialect": adapter,
            "store": {"adapter": adapter, "database": store_path},
            "retention_days": retention_days,
            "time_semantics": time_semantics,
            "bounds": filter_hint,
            "relations": items,
        });
        return format!("{document}\n");
    }
    let mut lines: Vec<String> = vec![
        format!("Recall store {store_path} ({dialect} dialect, retention {retention_days} days)"),
        format!("T{}; {filter_hint}.", &time_semantics[1..]),
    ];
    for relation in relations {
        lines.push(String::new());
        let note = relation_note(&relation.name);
        lines.push(if note.is_empty() {
            format!("{} ({})", relation.name, relation.kind)
        } else {
            format!("{} ({}): {note}", relation.name, relation.kind)
        });
        for column in &relation.columns {
            let key = if JOIN_KEYS.contains(&column.name.as_str()) {
                "  join key"
            } else {
                ""
            };
            let nullability = if column.nullable { "" } else { " not null" };
            lines.push(format!(
                "  {} {}{nullability}{key}",
                column.name,
                if column.declared_type.is_empty() {
                    "ANY"
                } else {
                    &column.declared_type
                }
            ));
        }
    }
    format!("{}\n", lines.join("\n"))
}
