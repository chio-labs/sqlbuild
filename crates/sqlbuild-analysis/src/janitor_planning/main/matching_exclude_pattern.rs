//! Janitor exclude patterns matched against relation and qualified names.

use sqlbuild_core::text::main::glob_match::glob_match;

/// The first pattern matching the name or the qualified display name, ignoring case.
#[must_use]
pub fn matching_exclude_pattern<'a>(
    (name, display_name): (&str, &str),
    patterns: &'a [String],
) -> Option<&'a str> {
    let name: String = name.to_lowercase();
    let display_name: String = display_name.to_lowercase();
    patterns
        .iter()
        .find(|pattern| {
            let folded: String = pattern.to_lowercase();
            glob_match(&name, &folded) || glob_match(&display_name, &folded)
        })
        .map(String::as_str)
}
