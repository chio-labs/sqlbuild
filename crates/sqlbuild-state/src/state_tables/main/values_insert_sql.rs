//! `values_insert_sql`: rows of rendered literals appended with one `INSERT ... VALUES`.

/// `INSERT INTO <table> (<columns>) VALUES (<row>), ...`.
pub fn values_insert_sql(qualified_name: &str, columns: &[&str], rows: &[Vec<String>]) -> String {
    let values: Vec<String> = rows
        .iter()
        .map(|row| format!("({})", row.join(", ")))
        .collect();
    format!(
        "INSERT INTO {qualified_name} ({}) VALUES {}",
        columns.join(", "),
        values.join(", ")
    )
}
