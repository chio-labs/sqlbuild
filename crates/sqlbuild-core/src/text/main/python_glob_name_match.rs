//! A `Path.glob` name match: `fnmatch.translate` compiled with or without `re.IGNORECASE`.

use crate::text::_helpers::fnmatch::code_points_match;
use crate::text::main::active_python_text::active_python_text;
use crate::text::main::python_ignorecase_key::python_ignorecase_key;

/// Whether the code points of `name`, lone surrogates included, match `pattern`.
#[must_use]
pub fn python_glob_name_match(name: &[u32], pattern: &str, ignore_case: bool) -> bool {
    if !ignore_case {
        return code_points_match(name, pattern);
    }
    let python = active_python_text();
    let key = |code_point: u32| {
        char::from_u32(code_point).map_or(code_point, |character| {
            u32::from(python_ignorecase_key(python, character))
        })
    };
    let folded_name: Vec<u32> = name.iter().map(|code_point| key(*code_point)).collect();
    let folded_pattern: String = pattern
        .chars()
        .map(|character| python_ignorecase_key(python, character))
        .collect();
    code_points_match(&folded_name, &folded_pattern)
}
