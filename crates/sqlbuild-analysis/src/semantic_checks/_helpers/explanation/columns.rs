//! Python's column suggestions: edit distance, evidence order and the closest column.

use std::cmp::Ordering;

use crate::semantic_checks::_helpers::sql_text::text::casefold;
use crate::semantic_checks::constants::{MAX_EDIT_DISTANCE, MIN_ABBREVIATION_LENGTH};
use crate::semantic_checks::models::SemanticFailure;

/// Python's `column_distance`: Levenshtein distance between case-folded names.
pub(crate) fn column_distance(left: &str, right: &str) -> usize {
    let left: Vec<char> = casefold(left).chars().collect();
    let right: Vec<char> = casefold(right).chars().collect();
    let mut row: Vec<usize> = (0..=right.len()).collect();
    for (i, a) in left.iter().enumerate() {
        let mut following: Vec<usize> = Vec::with_capacity(right.len() + 1);
        following.push(i + 1);
        for (j, b) in right.iter().enumerate() {
            let last = following[j];
            following.push(
                (last + 1)
                    .min(row[j + 1] + 1)
                    .min(row[j] + usize::from(a != b)),
            );
        }
        row = following;
    }
    row[right.len()]
}

/// Python's `ordered_columns`: columns by relative edit distance, then by name.
pub(crate) fn ordered_columns<'a>(
    name: &str,
    columns: &'a [(String, String)],
) -> Result<Vec<&'a str>, SemanticFailure> {
    let name_length: usize = name.chars().count();
    let mut keyed: Vec<(f64, &'a str)> = Vec::with_capacity(columns.len());
    for (column, _) in columns {
        let longest = name_length.max(column.chars().count()).max(1);
        keyed.push((
            column_distance(name, column) as f64 / longest as f64,
            column.as_str(),
        ));
    }
    keyed.sort_by(|left, right| {
        left.0
            .partial_cmp(&right.0)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.1.cmp(right.1))
    });
    Ok(keyed.into_iter().map(|(_, column)| column).collect())
}

/// Python's `closest_column`: the first ordered column within two edits or abbreviating the name.
pub(crate) fn closest_column<'a>(
    name: &str,
    columns: &'a [(String, String)],
) -> Result<Option<&'a str>, SemanticFailure> {
    let folded_name: Vec<char> = casefold(name).chars().collect();
    let name_first: String = folded_end(name, str::chars);
    let name_last: String = folded_end(name, |text| text.chars().rev());
    for candidate in ordered_columns(name, columns)? {
        let distance = column_distance(name, candidate);
        let folded_candidate: Vec<char> = casefold(candidate).chars().collect();
        let abbreviation = name.chars().count() >= MIN_ABBREVIATION_LENGTH
            && folded_end(candidate, str::chars) == name_first
            && folded_end(candidate, |text| text.chars().rev()) == name_last
            && is_subsequence(&folded_name, &folded_candidate);
        if distance <= MAX_EDIT_DISTANCE || abbreviation {
            return Ok(Some(candidate));
        }
    }
    Ok(None)
}

/// Python's `text[:1].casefold()` or `text[-1:].casefold()`, by the end `characters` reads first.
fn folded_end<'t, I: Iterator<Item = char>>(
    text: &'t str,
    characters: impl Fn(&'t str) -> I,
) -> String {
    characters(text)
        .next()
        .map_or_else(String::new, |character| casefold(&character.to_string()))
}

/// Python's `all(character in remaining for character in name)` over one shared iterator.
fn is_subsequence(name: &[char], candidate: &[char]) -> bool {
    let mut position: usize = 0;
    for character in name {
        match candidate[position..]
            .iter()
            .position(|value| value == character)
        {
            Some(offset) => position += offset + 1,
            None => return false,
        }
    }
    true
}
