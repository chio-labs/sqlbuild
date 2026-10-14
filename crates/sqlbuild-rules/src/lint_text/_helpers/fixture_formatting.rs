//! Schema-aware simplification of authored fixture projections.

use regex::Regex;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use std::collections::HashMap;
use std::sync::LazyLock;

static PATTERNS: LazyLock<Result<[Regex; 8], regex::Error>> = LazyLock::new(|| {
    Ok([
        Regex::new(concat!(
            r#"(?i)^[ \t]*(?:CAST\s*\(\s*NULL\s+AS\s+(?:"#,
            r#"[A-Za-z_][A-Za-z0-9_]*(?:\s*\([^()]*\))?"#,
            r#"(?:\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*\([^()]*\))?)*"#,
            r#")\)|NULL\s*::\s*(?:[A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?))"#,
            r#"\s+AS\s+(?P<alias>"[^"]+"|`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)(?:\s*,)?[ \t]*$"#,
        ))?,
        Regex::new(r"(?i)\b(?:UNION|INTERSECT|EXCEPT)\b")?,
        Regex::new(r"(?is)^\s*SELECT\s+(?P<projection>.+?)\s+WHERE\s+FALSE\s*$")?,
        Regex::new(r"(?i)^\s*SELECT\b(?P<body>.*)$")?,
        Regex::new(
            r"(?i)^\s*(?:FROM|WHERE|GROUP|HAVING|QUALIFY|ORDER|LIMIT|UNION|INTERSECT|EXCEPT)\b",
        )?,
        Regex::new(r#"(?i)\bAS\s+(?P<alias>"[^"]+"|`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)\s*,?\s*$"#)?,
        Regex::new(r",\s*$")?,
        Regex::new(r"(?i)^\s*SELECT\s+WHERE\s+FALSE\s*$")?,
    ])
});

/// Remove only typed-null projections that completion can reconstruct in schema order.
pub(crate) fn simplify_fixture_nulls(
    sql: &str,
    columns: &[(String, Option<String>, Option<bool>)],
) -> Result<String, regex::Error> {
    let [typed, set, empty, _, _, _, _, empty_remaining] =
        PATTERNS.as_ref().map_err(Clone::clone)?;
    if set.is_match(sql) {
        return Ok(sql.to_string());
    }
    let metadata_by_name: HashMap<String, &(String, Option<String>, Option<bool>)> = columns
        .iter()
        .map(|column| (python_casefold(&column.0), column))
        .collect();
    let known_column = |projection: &str| {
        typed.captures(projection).and_then(|captures| {
            let alias = python_casefold(captures["alias"].trim_matches(['"', '`']));
            metadata_by_name
                .get(&alias)
                .copied()
                .filter(|column| column.1.is_some())
        })
    };
    if let Some(query) = empty.captures(sql) {
        let projections = split_expressions(&query["projection"]);
        if !projections.is_empty()
            && projections
                .iter()
                .all(|projection| known_column(projection.trim()).is_some())
        {
            return Ok("SELECT * FROM __empty_fixture()".to_string());
        }
    }
    let lines: Vec<String> = python_splitlines(sql)
        .into_iter()
        .map(str::to_string)
        .collect();
    let mut empty_retained: Vec<String> = Vec::new();
    let mut retained: Vec<String> = Vec::new();
    let mut removed = false;
    for line in &lines {
        if let Some(column) = known_column(line) {
            if column.2 == Some(false) {
                retained.push(line.clone());
            } else {
                removed = true;
            }
        } else {
            empty_retained.push(line.clone());
            retained.push(line.clone());
        }
    }
    trim_comma(&mut empty_retained)?;
    if empty_remaining.is_match(&empty_retained.join("\n")) {
        return Ok("SELECT * FROM __empty_fixture()".to_string());
    }
    if !removed || !schema_prefix(&lines, columns)? {
        return Ok(sql.to_string());
    }
    trim_comma(&mut retained)?;
    if aliases(&retained)?.is_none_or(|names| names.is_empty())
        || !schema_prefix(&retained, columns)?
    {
        return Ok(sql.to_string());
    }
    Ok(retained.join("\n"))
}

fn split_expressions(value: &str) -> Vec<&str> {
    let mut expressions: Vec<&str> = Vec::new();
    let mut start = 0;
    let mut depth: usize = 0;
    let mut quote = None;
    let mut characters = value.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if let Some(delimiter) = quote {
            if character == delimiter {
                if characters
                    .peek()
                    .is_some_and(|(_, next)| *next == delimiter)
                {
                    characters.next();
                } else {
                    quote = None;
                }
            }
            continue;
        }
        match character {
            '\'' | '"' | '`' => quote = Some(character),
            '(' => depth += 1,
            ')' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                expressions.push(&value[start..index]);
                start = index + 1;
            }
            _ => {}
        }
    }
    expressions.push(&value[start..]);
    expressions
        .into_iter()
        .filter(|expression| !expression.trim().is_empty())
        .collect()
}

fn aliases(lines: &[String]) -> Result<Option<Vec<String>>, regex::Error> {
    let [_, _, _, select, clause, alias, _, _] = PATTERNS.as_ref().map_err(Clone::clone)?;
    let mut saw_select = false;
    let mut names: Vec<String> = Vec::new();
    for line in lines {
        let mut candidate = line.as_str();
        if !saw_select {
            if let Some(captures) = select.captures(line) {
                saw_select = true;
                candidate = captures.name("body").map_or("", |body| body.as_str());
            } else if line.trim().is_empty() {
                continue;
            } else {
                return Ok(None);
            }
        }
        if clause.is_match(candidate) {
            break;
        }
        if candidate.trim().is_empty() {
            continue;
        }
        let Some(captures) = alias.captures(candidate) else {
            return Ok(None);
        };
        names.push(python_casefold(captures["alias"].trim_matches(['"', '`'])));
    }
    Ok(saw_select.then_some(names))
}

fn schema_prefix(
    lines: &[String],
    columns: &[(String, Option<String>, Option<bool>)],
) -> Result<bool, regex::Error> {
    Ok(aliases(lines)?.is_some_and(|names| {
        names.iter().eq(columns
            .iter()
            .take(names.len())
            .map(|column| python_casefold(&column.0))
            .collect::<Vec<_>>()
            .iter())
    }))
}

fn trim_comma(lines: &mut [String]) -> Result<(), regex::Error> {
    let [_, _, _, _, clause, _, trailing, _] = PATTERNS.as_ref().map_err(Clone::clone)?;
    let end = lines
        .iter()
        .position(|line| clause.is_match(line))
        .unwrap_or(lines.len());
    if let Some(line) = lines[..end]
        .iter_mut()
        .rev()
        .find(|line| !line.trim().is_empty())
    {
        *line = trailing.replace(line, "").into_owned();
    }
    Ok(())
}
