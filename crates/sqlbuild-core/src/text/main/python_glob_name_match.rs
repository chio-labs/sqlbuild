//! A `Path.glob` name match: `fnmatch.translate` compiled with or without `re.IGNORECASE`.

use crate::text::main::active_python_text::active_python_text;
use crate::text::main::python_fnmatchcase::python_fnmatchcase;
use crate::text::main::python_ignorecase_key::python_ignorecase_key;

/// Whether `name` matches `pattern`, ignoring case per Python's `re.IGNORECASE` keys if asked.
#[must_use]
pub fn python_glob_name_match(name: &str, pattern: &str, ignore_case: bool) -> bool {
    if !ignore_case {
        return python_fnmatchcase(name, pattern);
    }
    let python = active_python_text();
    let folded_name: String = name
        .chars()
        .map(|character| python_ignorecase_key(python, character))
        .collect();
    let folded_pattern: String = pattern
        .chars()
        .map(|character| python_ignorecase_key(python, character))
        .collect();
    python_fnmatchcase(&folded_name, &folded_pattern)
}
