//! Python's `re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", sql, re.IGNORECASE) is not None`.

use sqlbuild_core::text::main::ignorecase_key::ignorecase_key;
use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::assembly::analysis_session::constants::SET_OPERATION_KEYWORDS;

/// Whether `sql` names a set-operation keyword as a whole word, in any case.
pub fn names_set_operation(sql: &str) -> bool {
    let characters: Vec<char> = sql.chars().collect();
    for start in 0..characters.len() {
        if start > 0 && is_word_char(characters[start - 1]) {
            continue;
        }
        for keyword in SET_OPERATION_KEYWORDS {
            let end = start + keyword.len();
            if end > characters.len() {
                continue;
            }
            let matches = characters[start..end]
                .iter()
                .zip(keyword.chars())
                .all(|(character, letter)| ignorecase_key(*character) == letter);
            let bounded = characters.get(end).is_none_or(|next| !is_word_char(*next));
            if matches && bounded {
                return true;
            }
        }
    }
    false
}
