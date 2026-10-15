//! `relevant_sources_sql`: a latest-state read narrowed to the named sources.

/// `read_sql` filtered to `source_names`, each quoted as a SQL string literal.
pub fn relevant_sources_sql(read_sql: &str, source_names: &[String]) -> String {
    let literals: Vec<String> = source_names
        .iter()
        .map(|name| format!("'{}'", name.replace('\'', "''")))
        .collect();
    format!(
        "SELECT * FROM ({read_sql}) AS __sqlbuild_relevant WHERE source_name IN ({})",
        literals.join(", ")
    )
}
