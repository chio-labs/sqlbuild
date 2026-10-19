//! `clickhouse_relation`: a Recall table or view name as ClickHouse SQL refers to it.

use crate::schema::_helpers::rendering::clickhouse_table;
use crate::schema::models::DdlOptions;

/// `` `database`.`name` `` with the configured database, else `` `name` ``.
#[must_use]
pub fn clickhouse_relation(name: &str, options: &DdlOptions) -> String {
    clickhouse_table(name, options)
}
