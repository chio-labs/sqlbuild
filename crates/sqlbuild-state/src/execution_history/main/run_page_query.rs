//! `run_page_query`: one page of projected runs after a `(created_at, run_id)` key.

use crate::execution_history::_helpers::dialects::{placeholder, run_table, timestamp_param};
use crate::execution_history::models::{Dialect, Query, RunCursorKey, RunFilterSpec, SqlParam};

/// `SELECT *` of runs after `after` matching the filter, one row past `limit`.
pub fn run_page_query(
    dialect: Dialect,
    after: Option<&RunCursorKey>,
    run_filter: &RunFilterSpec,
    limit: i64,
) -> Query {
    let mark: &str = placeholder(dialect);
    let mut conditions: Vec<String> = Vec::new();
    let mut params: Vec<SqlParam> = Vec::new();
    if let Some(after) = after {
        match dialect {
            Dialect::Sqlite => {
                conditions.push("(created_at > ? OR (created_at = ? AND run_id > ?))".to_owned());
                params.push(SqlParam::Text(after.created_at_text.clone()));
                params.push(SqlParam::Text(after.created_at_text.clone()));
            }
            Dialect::Postgres => {
                conditions.push("(created_at, run_id) > (%s, %s)".to_owned());
                params.push(SqlParam::Timestamp(after.created_at));
            }
        }
        params.push(SqlParam::Text(after.run_id.clone()));
    }
    if let Some(invocation_id) = &run_filter.invocation_id {
        conditions.push(format!("invocation_id = {mark}"));
        params.push(SqlParam::Text(invocation_id.clone()));
    }
    if !run_filter.statuses.is_empty() {
        let statuses: Vec<String> = run_filter
            .statuses
            .iter()
            .map(|status| status.value().to_owned())
            .collect();
        match dialect {
            Dialect::Sqlite => {
                let marks: Vec<&str> = vec![mark; statuses.len()];
                conditions.push(format!("status IN ({})", marks.join(",")));
                params.extend(statuses.into_iter().map(SqlParam::Text));
            }
            Dialect::Postgres => {
                conditions.push(format!("status = ANY({mark})"));
                params.push(SqlParam::TextList(statuses));
            }
        }
    }
    for (comparison, bound) in [
        (">=", &run_filter.created_at_start),
        ("<=", &run_filter.created_at_end),
    ] {
        if let Some(bound) = bound {
            conditions.push(format!("created_at {comparison} {mark}"));
            params.push(timestamp_param(dialect, &bound.instant));
        }
    }
    let filter: String = if conditions.is_empty() {
        String::new()
    } else {
        format!(" WHERE {}", conditions.join(" AND "))
    };
    params.push(SqlParam::Integer(limit + 1));
    Query {
        sql: format!(
            "SELECT * FROM {}{filter} ORDER BY created_at, run_id LIMIT {mark}",
            run_table(dialect)
        ),
        params,
    }
}
