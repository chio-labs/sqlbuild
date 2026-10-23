//! Matching of rule failures before and after a refactoring.

use crate::refactor_command::constants::NUMBER_PLACEHOLDER;
use crate::refactor_command::models::RefactorDiagnostic;
use crate::refactoring::models::FileChange;

/// The index of the first unused earlier failure `matches` accepts.
pub(crate) fn first_unused(
    before: &[RefactorDiagnostic],
    used: &[bool],
    matches: impl Fn(&RefactorDiagnostic) -> bool,
) -> Option<usize> {
    before
        .iter()
        .zip(used)
        .position(|(earlier, used)| !*used && matches(earlier))
}

/// The path a moved file had before the change, or `path` itself.
pub(crate) fn original_path(changes: &[FileChange], path: Option<&str>) -> Option<String> {
    let path: &str = path?;
    let moved: Option<&FileChange> = changes
        .iter()
        .find(|change| change.moved() && change.path == path);
    Some(moved.map_or_else(|| path.to_owned(), |change| change.original_path.clone()))
}

/// Whether `after` is `before` with every number kept or lowered and nothing else changed.
pub(crate) fn reduced(before: &str, after: &str) -> bool {
    let (before_text, before_numbers) = numbers_apart(before);
    let (after_text, after_numbers) = numbers_apart(after);
    before_text == after_text
        && before_numbers.len() == after_numbers.len()
        && before_numbers
            .iter()
            .zip(&after_numbers)
            .all(|(earlier, later)| later <= earlier)
}

/// `message` with each run of ASCII digits replaced by a placeholder, and those numbers.
fn numbers_apart(message: &str) -> (String, Vec<(usize, String)>) {
    let mut text: String = String::new();
    let mut numbers: Vec<(usize, String)> = Vec::new();
    let mut digits: String = String::new();
    for character in message.chars() {
        if character.is_ascii_digit() {
            digits.push(character);
            continue;
        }
        if let Some(number) = number_of(&digits) {
            numbers.push(number);
            text.push(NUMBER_PLACEHOLDER);
        }
        digits.clear();
        text.push(character);
    }
    if let Some(number) = number_of(&digits) {
        numbers.push(number);
        text.push(NUMBER_PLACEHOLDER);
    }
    (text, numbers)
}

/// A run of digits as `(significant length, digits)`, which orders by value; none when empty.
fn number_of(digits: &str) -> Option<(usize, String)> {
    if digits.is_empty() {
        return None;
    }
    let significant: &str = digits.trim_start_matches('0');
    Some((significant.len(), significant.to_owned()))
}
