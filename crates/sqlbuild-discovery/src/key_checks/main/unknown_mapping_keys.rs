//! Python's `reject_unknown_mapping_keys`: keys of an authored mapping outside its allowed set.

use crate::_helpers::suggestions::unsupported_keys_help;

/// The message after `{file} {label}` and the help when a `(str(key), is str)` key is not allowed.
pub fn unknown_mapping_keys(
    keys: &[(String, bool)],
    allowed: &[String],
) -> Option<(String, String)> {
    let mut unknown: Vec<&str> = keys
        .iter()
        .filter(|(text, is_text)| !*is_text || !allowed.contains(text))
        .map(|(text, _)| text.as_str())
        .collect();
    if unknown.is_empty() {
        return None;
    }
    unknown.sort_unstable();
    let mut allowed_sorted: Vec<&str> = allowed.iter().map(String::as_str).collect();
    allowed_sorted.sort_unstable();
    Some((
        format!(
            "has unknown keys: {}; allowed keys: {}",
            unknown.join(", "),
            allowed_sorted.join(", ")
        ),
        unsupported_keys_help(&unknown, allowed),
    ))
}
