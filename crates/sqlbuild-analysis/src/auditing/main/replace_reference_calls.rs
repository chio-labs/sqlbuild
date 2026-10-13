//! Rewrite `function("name")` reference calls the way Python's `re.sub` over them does.

/// Replace each `function("name")` call, left to right without overlap; `None` keeps the call.
pub fn replace_reference_calls<E>(
    sql: &str,
    function: &str,
    mut replace: impl FnMut(&str) -> Result<Option<String>, E>,
) -> Result<String, E> {
    let opening: String = format!("{function}(\"");
    let mut rewritten: String = String::with_capacity(sql.len());
    let mut position: usize = 0;
    let mut search: usize = 0;
    while let Some(found) = sql[search..].find(&opening) {
        let start: usize = search + found;
        let name_start: usize = start + opening.len();
        let Some(name_length) = sql[name_start..].find('"') else {
            break;
        };
        let name_end: usize = name_start + name_length;
        if name_length == 0 || !sql[name_end + 1..].starts_with(')') {
            search = start + 1;
            continue;
        }
        let end: usize = name_end + 2;
        rewritten.push_str(&sql[position..start]);
        match replace(&sql[name_start..name_end])? {
            Some(replacement) => rewritten.push_str(&replacement),
            None => rewritten.push_str(&sql[start..end]),
        }
        position = end;
        search = end;
    }
    rewritten.push_str(&sql[position..]);
    Ok(rewritten)
}
