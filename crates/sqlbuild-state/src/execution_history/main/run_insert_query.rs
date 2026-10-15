//! `run_insert_query`: the insert of one projected run.

use crate::execution_history::_helpers::dialects::{
    optional_text_param, optional_timestamp_param, timestamp_param,
};
use crate::execution_history::constants::{POSTGRES_RUN_INSERT, SCHEMA_VERSION, SQLITE_RUN_INSERT};
use crate::execution_history::models::{Dialect, Query, RunRow, SqlParam};

/// SQLite stores `is_complete` as an integer, PostgreSQL as a boolean.
pub fn run_insert_query(dialect: Dialect, run: &RunRow) -> Query {
    let is_complete: SqlParam = match dialect {
        Dialect::Sqlite => SqlParam::Integer(i64::from(run.is_complete)),
        Dialect::Postgres => SqlParam::Flag(run.is_complete),
    };
    let sql: &str = match dialect {
        Dialect::Sqlite => SQLITE_RUN_INSERT,
        Dialect::Postgres => POSTGRES_RUN_INSERT,
    };
    Query {
        sql: sql.to_owned(),
        params: vec![
            SqlParam::Text(run.run_id.clone()),
            SqlParam::Text(run.invocation_id.clone()),
            timestamp_param(dialect, &run.created_at),
            SqlParam::Text(run.status.value().to_owned()),
            is_complete,
            SqlParam::Text(run.last_event_cursor.clone()),
            SqlParam::Integer(run.last_storage_order),
            optional_text_param(run.command.as_ref()),
            optional_text_param(run.target.as_ref()),
            optional_text_param(run.environment.as_ref()),
            optional_timestamp_param(dialect, run.started_at.as_ref()),
            optional_timestamp_param(dialect, run.ended_at.as_ref()),
            SqlParam::Integer(SCHEMA_VERSION),
        ],
    }
}
