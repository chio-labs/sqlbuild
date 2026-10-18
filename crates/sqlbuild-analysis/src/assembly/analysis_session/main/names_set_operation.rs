//! Python's `re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", sql, re.IGNORECASE) is not None`.

use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::assembly::analysis_session::constants::SET_OPERATION_KEYWORDS;

/// Whether a whole word of `sql` is a set-operation keyword; only ASCII letters fold to its letters.
pub fn names_set_operation(sql: &str) -> bool {
    sql.split(|character: char| !is_word_char(character))
        .any(is_set_operation_keyword)
}

/// Whether `word` is a set-operation keyword, ignoring ASCII case.
fn is_set_operation_keyword(word: &str) -> bool {
    SET_OPERATION_KEYWORDS
        .iter()
        .any(|keyword| word.eq_ignore_ascii_case(keyword))
}
