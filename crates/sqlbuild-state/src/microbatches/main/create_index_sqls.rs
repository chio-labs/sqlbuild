//! `create_index_sqls`: the non-unique scope and provenance indexes of the state table.

/// One `CREATE INDEX IF NOT EXISTS` per rendered index name and its rendered columns.
#[must_use]
pub fn create_index_sqls(table: &str, indexes: &[(String, Vec<String>)]) -> Vec<String> {
    indexes
        .iter()
        .map(|(name, columns)| {
            format!(
                "CREATE INDEX IF NOT EXISTS {name} ON {table} ({})",
                columns.join(", ")
            )
        })
        .collect()
}
