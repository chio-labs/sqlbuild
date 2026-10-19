//! Python's `_prepared_test_sql` and `_REFERENCE_CALL_PATTERN`: test SQL with empty fixtures opened.

use crate::semantic_checks::_helpers::resource_sql::scanning::{
    literal, slice, spaces, starts_word, words,
};

const REFERENCE_KINDS: [&str; 3] = ["ref", "source", "seed"];
const FIXTURE_KINDS: [&str; 4] = ["ref", "source", "seed", "expected"];
const EMPTY_FIXTURE: &str = "__empty_fixture";
const OPEN_EMPTY_FIXTURE_RELATION: &str = "__sqlbuild_empty_fixture";
const QUOTES: [char; 2] = ['\'', '"'];

/// `__(?:ref|source|seed)\(\s*['"]([^'"]+)['"]\s*\)` at `index`: the name and match end.
fn reference_call(text: &[char], index: usize) -> Option<(String, usize)> {
    let after = literal(text, index, "__", false)?;
    let after = REFERENCE_KINDS
        .iter()
        .find_map(|kind| literal(text, after, kind, false))?;
    let after = spaces(text, literal(text, after, "(", false)?, false)?;
    if !QUOTES.contains(text.get(after)?) {
        return None;
    }
    let name_end = after
        + 1
        + text[after + 1..]
            .iter()
            .take_while(|character| !QUOTES.contains(character))
            .count();
    if name_end == after + 1 || !QUOTES.contains(text.get(name_end)?) {
        return None;
    }
    let end = literal(text, spaces(text, name_end + 1, false)?, ")", false)?;
    Some((slice(text, after + 1, name_end), end))
}

/// `findall` of the reference call pattern over `text`.
pub(crate) fn reference_names(text: &[char]) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    let mut index = 0;
    while index < text.len() {
        match reference_call(text, index) {
            Some((name, end)) => {
                names.push(name);
                index = end;
            }
            None => index += 1,
        }
    }
    names
}

/// `\b__empty_fixture\s*\(\s*\)` (ignoring case) at `index`: the match end.
fn empty_fixture_call(text: &[char], index: usize) -> Option<usize> {
    if !starts_word(text, index) {
        return None;
    }
    let after = spaces(text, literal(text, index, EMPTY_FIXTURE, true)?, false)?;
    let after = spaces(text, literal(text, after, "(", false)?, false)?;
    literal(text, after, ")", false)
}

/// The empty fixture CTE at `index`: its prefix end, fixture name, and match end.
fn empty_fixture_cte(text: &[char], index: usize) -> Option<(usize, String, usize)> {
    if !starts_word(text, index) {
        return None;
    }
    let after = literal(text, index, "__", false)?;
    let after = FIXTURE_KINDS
        .iter()
        .find_map(|kind| literal(text, after, kind, true))?;
    let name_start = literal(text, after, "__", false)?;
    let name_end = words(text, name_start)?;
    let after = spaces(text, name_end, true)?;
    let after = spaces(text, literal(text, after, "AS", true)?, false)?;
    let after = spaces(text, literal(text, after, "(", false)?, false)?;
    let after = spaces(text, literal(text, after, "SELECT", true)?, true)?;
    let after = spaces(text, literal(text, after, "*", false)?, true)?;
    let prefix_end = spaces(text, literal(text, after, "FROM", true)?, true)?;
    let end = empty_fixture_call_body(text, prefix_end)?;
    Some((prefix_end, slice(text, name_start, name_end), end))
}

/// `__empty_fixture\s*\(\s*\)` (ignoring case) at `index`, without a word boundary.
fn empty_fixture_call_body(text: &[char], index: usize) -> Option<usize> {
    let after = spaces(text, literal(text, index, EMPTY_FIXTURE, true)?, false)?;
    let after = spaces(text, literal(text, after, "(", false)?, false)?;
    literal(text, after, ")", false)
}

/// One empty fixture CTE: where it starts, where its prefix ends, its name and its end.
struct EmptyFixtureCte {
    start: usize,
    prefix_end: usize,
    name: String,
    end: usize,
}

/// Every empty fixture CTE in `text`.
fn empty_fixture_ctes(text: &[char]) -> Vec<EmptyFixtureCte> {
    let mut found: Vec<EmptyFixtureCte> = Vec::new();
    let mut index = 0;
    while index < text.len() {
        match empty_fixture_cte(text, index) {
            Some((prefix_end, name, end)) => {
                found.push(EmptyFixtureCte {
                    start: index,
                    prefix_end,
                    name,
                    end,
                });
                index = end;
            }
            None => index += 1,
        }
    }
    found
}

/// Test SQL with empty fixture CTEs reading their own name and other empty fixtures opened.
pub(crate) fn prepared_test_sql(sql_body: &str) -> (String, Vec<String>) {
    let body: Vec<char> = sql_body.chars().collect();
    let ctes = empty_fixture_ctes(&body);
    let mut opened: Vec<char> = Vec::with_capacity(body.len());
    let mut copied = 0;
    for cte in &ctes {
        opened.extend_from_slice(&body[copied..cte.start]);
        opened.extend_from_slice(&body[cte.start..cte.prefix_end]);
        opened.extend(cte.name.chars());
        copied = cte.end;
    }
    opened.extend_from_slice(&body[copied..]);
    let mut sql = String::with_capacity(opened.len());
    let mut index = 0;
    while index < opened.len() {
        if let Some(end) = empty_fixture_call(&opened, index) {
            sql.push_str(OPEN_EMPTY_FIXTURE_RELATION);
            index = end;
        } else {
            sql.push(opened[index]);
            index += 1;
        }
    }
    let mut relations = reference_names(&body);
    relations.extend(ctes.into_iter().map(|cte| cte.name));
    (sql, relations)
}
