//! `table_columns`: every column of one table, its own then the common columns.

use crate::schema::_helpers::rendering::all_columns;
use crate::schema::main::table_spec::table_spec;
use crate::schema::models::{ColumnSpec, Table};

/// The table's columns in DDL order.
#[must_use]
pub fn table_columns(table: Table) -> Vec<ColumnSpec> {
    all_columns(table_spec(table))
}
