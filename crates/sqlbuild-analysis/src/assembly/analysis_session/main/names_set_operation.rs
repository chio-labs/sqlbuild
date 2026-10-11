//! Python's `re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", sql, re.IGNORECASE) is not None`.

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_word::is_python_word;
use sqlbuild_core::text::main::python_ignorecase_key::python_ignorecase_key;

use crate::assembly::analysis_session::constants::SET_OPERATION_KEYWORDS;

/// Whether `sql` names a set-operation keyword as a whole word, in any case.
pub fn names_set_operation(sql: &str) -> bool {
    let python = active_python_text();
    let characters: Vec<char> = sql.chars().collect();
    for start in 0..characters.len() {
        if start > 0 && is_python_word(python, characters[start - 1]) {
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
                .all(|(character, letter)| python_ignorecase_key(python, *character) == letter);
            let bounded = characters
                .get(end)
                .is_none_or(|next| !is_python_word(python, *next));
            if matches && bounded {
                return true;
            }
        }
    }
    false
}
