//! Ordered aliases declared by table and view models.

/// Strip origin names and sort aliases, retaining duplicates exactly as declared.
pub fn declared_column_aliases(columns: &[(String, Option<String>)]) -> Vec<(String, String)> {
    let mut aliases: Vec<(String, String)> = Vec::new();
    for (name, origin) in columns {
        if let Some(origin) = origin {
            aliases.push((origin.trim().to_owned(), name.clone()));
        }
    }
    aliases.sort();
    aliases
}
