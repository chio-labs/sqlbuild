//! Python's `normalize_query_sql`: `re.sub(r"\s+", " ", sql.strip())`.

/// `sql` stripped, with every run of Python whitespace collapsed to one space.
pub fn normalized_query_text(sql: &str) -> String {
    let mut normalized = String::with_capacity(sql.len());
    let mut in_space = false;
    for character in str::trim(sql).chars() {
        if char::is_whitespace(character) {
            if !in_space {
                normalized.push(' ');
            }
            in_space = true;
        } else {
            normalized.push(character);
            in_space = false;
        }
    }
    normalized
}
