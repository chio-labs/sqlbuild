//! The `TARGET DESTINATION` or `TARGET NEW_NAME` pairs of one `sqb mv` or `sqb rename`.

use crate::refactor_command::constants::{
    MOVE_FILE_COMMENT, MOVE_PAIRS_USAGE, RENAME_PAIRS_USAGE, TARGET_ERROR_CODE,
};
use crate::refactor_command::models::PairArguments;
use crate::refactoring::errors::RefactorError;

/// Every `(target, second)` pair in command-line order, then in file order.
pub fn refactor_pairs(
    arguments: &PairArguments<'_>,
) -> Result<Vec<(String, String)>, RefactorError> {
    let (command, second, usage) = if arguments.is_move {
        ("sqb mv", "DESTINATION", MOVE_PAIRS_USAGE)
    } else {
        ("sqb rename", "NEW_NAME", RENAME_PAIRS_USAGE)
    };
    let words: &[&str] = &arguments.words;
    if words.len() % 2 == 1 {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            format!("'{}' has no {second}", words[words.len() - 1]),
            Some(usage),
        ));
    }
    let mut pairs: Vec<(String, String)> = words
        .chunks(2)
        .map(|pair| (pair[0].to_owned(), pair[1].to_owned()))
        .collect();
    if let Some((path, contents)) = arguments.file {
        pairs.extend(file_pairs((path, contents), second, usage)?);
    }
    if pairs.is_empty() {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            format!("{command} needs a TARGET and a {second}"),
            Some(usage),
        ));
    }
    Ok(pairs)
}

/// The pairs of a pair file: one per line, two whitespace-separated words, `#` comments.
fn file_pairs(
    (path, contents): (&str, &str),
    second: &str,
    usage: &str,
) -> Result<Vec<(String, String)>, RefactorError> {
    let mut pairs: Vec<(String, String)> = Vec::new();
    for (number, line) in contents.lines().enumerate() {
        let text: &str = line.trim();
        if text.is_empty() || text.starts_with(MOVE_FILE_COMMENT) {
            continue;
        }
        let words: Vec<&str> = text.split_whitespace().collect();
        let [target, other] = words.as_slice() else {
            return Err(RefactorError::input(
                TARGET_ERROR_CODE,
                format!(
                    "{path}:{}: expected TARGET and {second} separated by a tab or spaces, \
                     found {} words",
                    number + 1,
                    words.len()
                ),
                Some(usage),
            ));
        };
        pairs.push(((*target).to_owned(), (*other).to_owned()));
    }
    Ok(pairs)
}
