//! The `TARGET DESTINATION` pairs of one `sqb mv`, from the command line and `--from-file`.

use crate::refactor_command::constants::{MOVE_FILE_COMMENT, MOVE_PAIRS_USAGE, TARGET_ERROR_CODE};
use crate::refactor_command::models::MoveArguments;
use crate::refactoring::errors::RefactorError;

/// Every `(target, destination)` pair in command-line order, then in file order.
pub fn move_pairs(arguments: &MoveArguments<'_>) -> Result<Vec<(String, String)>, RefactorError> {
    let words: &[&str] = &arguments.words;
    if words.len() % 2 == 1 {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            format!("'{}' has no DESTINATION", words[words.len() - 1]),
            Some(MOVE_PAIRS_USAGE),
        ));
    }
    let mut pairs: Vec<(String, String)> = words
        .chunks(2)
        .map(|pair| (pair[0].to_owned(), pair[1].to_owned()))
        .collect();
    if let Some((path, contents)) = arguments.file {
        pairs.extend(file_pairs(path, contents)?);
    }
    if pairs.is_empty() {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            "sqb mv needs a TARGET and a DESTINATION",
            Some(MOVE_PAIRS_USAGE),
        ));
    }
    Ok(pairs)
}

/// The pairs of a move file: one per line, two whitespace-separated words, `#` comments.
fn file_pairs(path: &str, contents: &str) -> Result<Vec<(String, String)>, RefactorError> {
    let mut pairs: Vec<(String, String)> = Vec::new();
    for (number, line) in contents.lines().enumerate() {
        let text: &str = line.trim();
        if text.is_empty() || text.starts_with(MOVE_FILE_COMMENT) {
            continue;
        }
        let words: Vec<&str> = text.split_whitespace().collect();
        let [target, destination] = words.as_slice() else {
            return Err(RefactorError::input(
                TARGET_ERROR_CODE,
                format!(
                    "{path}:{}: expected TARGET and DESTINATION separated by a tab or spaces, \
                     found {} words",
                    number + 1,
                    words.len()
                ),
                Some(MOVE_PAIRS_USAGE),
            ));
        };
        pairs.push(((*target).to_owned(), (*destination).to_owned()));
    }
    Ok(pairs)
}
