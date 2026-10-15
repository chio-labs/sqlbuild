//! `event_insert_query`: the insert of one prepared event with its envelope.

use crate::execution_history::_helpers::dialects::{
    optional_text_param, optional_timestamp_param, timestamp_param,
};
use crate::execution_history::constants::{POSTGRES_EVENT_INSERT, SQLITE_EVENT_INSERT};
use crate::execution_history::models::{Dialect, PreparedEvent, Query, SqlParam};
use crate::execution_history::types::UtcTime;

/// SQLite stores `received_at` from the caller; PostgreSQL stores `producer_version` instead.
pub fn event_insert_query(dialect: Dialect, event: &PreparedEvent, received_at: &UtcTime) -> Query {
    let envelope = &event.envelope;
    let [producer, producer_version, event_type, correlations @ ..] = &envelope.text_fields;
    let mut params: Vec<SqlParam> = vec![
        SqlParam::Text(event.event_id.clone()),
        SqlParam::Integer(envelope.schema_version),
        optional_text_param(producer.as_ref()),
    ];
    if dialect == Dialect::Postgres {
        params.push(optional_text_param(producer_version.as_ref()));
    }
    params.push(optional_text_param(event_type.as_ref()));
    params.push(optional_timestamp_param(
        dialect,
        envelope.occurred_at.as_ref(),
    ));
    if dialect == Dialect::Sqlite {
        params.push(timestamp_param(dialect, received_at));
    }
    params.extend(
        correlations
            .iter()
            .map(|value| optional_text_param(value.as_ref())),
    );
    params.push(SqlParam::Text(event.content.clone()));
    params.push(SqlParam::Text(event.digest.clone()));
    let sql: &str = match dialect {
        Dialect::Sqlite => SQLITE_EVENT_INSERT,
        Dialect::Postgres => POSTGRES_EVENT_INSERT,
    };
    Query {
        sql: sql.to_owned(),
        params,
    }
}
