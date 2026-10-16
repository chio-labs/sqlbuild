//! Runs of rejected characters collapsed to one separator.

use crate::dagster_invocation::constants::NAME_SEPARATOR;

/// `value` with every maximal run of characters `kept` rejects replaced by one `_`.
pub(crate) fn replace_runs(value: &str, kept: impl Fn(char) -> bool) -> String {
    let mut replaced: String = String::with_capacity(value.len());
    let mut in_run: bool = false;
    for character in value.chars() {
        if kept(character) {
            replaced.push(character);
            in_run = false;
        } else if !in_run {
            replaced.push(NAME_SEPARATOR);
            in_run = true;
        }
    }
    replaced
}
