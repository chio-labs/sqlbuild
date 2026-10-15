//! `event_page_query`: one ascending page of lifecycle events after a storage position.

use crate::execution_history::_helpers::dialects::{event_table, placeholder, timestamp_param};
use crate::execution_history::models::{Dialect, EventFilterSpec, Query, SqlParam};

/// `SELECT *` of events after `after_storage_id` matching the filter, one row past `limit`.
pub fn event_page_query(
    dialect: Dialect,
    after_storage_id: i64,
    event_filter: &EventFilterSpec,
    limit: i64,
) -> Query {
    let mark: &str = placeholder(dialect);
    let mut conditions: Vec<String> = vec![format!("storage_id > {mark}")];
    let mut params: Vec<SqlParam> = vec![SqlParam::Integer(after_storage_id)];
    for (column, value) in [
        ("invocation_id", &event_filter.invocation_id),
        ("run_id", &event_filter.run_id),
        ("producer", &event_filter.producer),
    ] {
        if let Some(value) = value {
            conditions.push(format!("{column} = {mark}"));
            params.push(SqlParam::Text(value.clone()));
        }
    }
    if !event_filter.event_types.is_empty() {
        match dialect {
            Dialect::Sqlite => {
                let marks: Vec<&str> = vec![mark; event_filter.event_types.len()];
                conditions.push(format!("event_type IN ({})", marks.join(",")));
                params.extend(event_filter.event_types.iter().cloned().map(SqlParam::Text));
            }
            Dialect::Postgres => {
                conditions.push(format!("event_type = ANY({mark})"));
                params.push(SqlParam::TextList(event_filter.event_types.clone()));
            }
        }
    }
    if let Some(family) = &event_filter.family {
        conditions.push(format!("event_type LIKE {mark}"));
        params.push(SqlParam::Text(format!("{family}_%")));
    }
    for (comparison, bound) in [
        (">=", &event_filter.occurred_at_start),
        ("<=", &event_filter.occurred_at_end),
    ] {
        if let Some(bound) = bound {
            conditions.push(format!("occurred_at {comparison} {mark}"));
            params.push(timestamp_param(dialect, &bound.instant));
        }
    }
    params.push(SqlParam::Integer(limit + 1));
    Query {
        sql: format!(
            "SELECT * FROM {} WHERE {} ORDER BY storage_id ASC LIMIT {mark}",
            event_table(dialect),
            conditions.join(" AND ")
        ),
        params,
    }
}
