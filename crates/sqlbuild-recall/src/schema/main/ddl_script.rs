//! `ddl_script`: the complete ordered script an administrator runs to create a Recall store.

use crate::schema::main::table_statements::table_statements;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::{DdlOptions, Dialect};

/// Every table, index and view statement, each terminated by `;`.
#[must_use]
pub fn ddl_script(dialect: Dialect, options: &DdlOptions) -> String {
    let mut statements: Vec<String> = table_statements(dialect, options);
    statements.extend(
        view_statements(dialect, options)
            .into_iter()
            .map(|(_, statement)| statement),
    );
    let mut script: String = statements.join(";\n\n");
    script.push_str(";\n");
    script
}
