//! Python's `validate_sql_test_names`: every block of a multi-block file has a unique name.

/// Why the blocks' `(test_index, name)` pairs are invalid, if they are.
pub fn sql_test_names_failure(
    file_path: &str,
    blocks: &[(usize, Option<String>)],
) -> Option<String> {
    if blocks.len() <= 1 {
        return None;
    }
    let unnamed: Vec<String> = blocks
        .iter()
        .filter(|(_, name)| name.is_none())
        .map(|(index, _)| index.to_string())
        .collect();
    if !unnamed.is_empty() {
        return Some(format!(
            "SQL test '{file_path}' contains multiple TEST blocks; every block must define a \
             unique `name`. Missing names for blocks: {}",
            unnamed.join(", ")
        ));
    }
    let mut seen: Vec<&str> = Vec::new();
    for name in blocks.iter().filter_map(|(_, name)| name.as_deref()) {
        if seen.contains(&name) {
            return Some(format!(
                "SQL test '{file_path}' defines duplicate TEST() name '{name}'"
            ));
        }
        seen.push(name);
    }
    None
}
