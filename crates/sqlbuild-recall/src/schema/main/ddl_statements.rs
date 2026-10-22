//! `ddl_statements`: every statement that creates a Recall store, in order.

use crate::schema::_helpers::version_row::version_row_statement;
use crate::schema::main::table_statements::table_statements;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::{DdlOptions, Dialect};

/// Every table, index and view statement, then the schema version row.
#[must_use]
pub fn ddl_statements(dialect: Dialect, options: &DdlOptions) -> Vec<String> {
    let mut statements: Vec<String> = table_statements(dialect, options);
    statements.extend(
        view_statements(dialect, options)
            .into_iter()
            .map(|(_, statement)| statement),
    );
    statements.push(version_row_statement(dialect, options));
    statements
}
