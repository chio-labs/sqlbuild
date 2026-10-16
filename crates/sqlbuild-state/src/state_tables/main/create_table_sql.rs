//! `create_table_sql`: create-if-missing DDL for one append-only state table.

use crate::state_tables::models::TableColumn;

/// `CREATE TABLE IF NOT EXISTS <table> (<name> <type>[ NOT NULL], ...)`.
pub fn create_table_sql(qualified_name: &str, columns: &[TableColumn]) -> String {
    let definitions: Vec<String> = columns
        .iter()
        .map(|column| {
            let required: &str = if column.required { " NOT NULL" } else { "" };
            format!("{} {}{required}", column.name, column.rendered_type)
        })
        .collect();
    format!(
        "CREATE TABLE IF NOT EXISTS {qualified_name} ({})",
        definitions.join(", ")
    )
}
