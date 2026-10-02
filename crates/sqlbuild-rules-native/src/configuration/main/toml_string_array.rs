//! TOML array rendering for remediation snippets.

/// A TOML array of strings, in the given order.
pub(crate) fn toml_string_array<'a>(values: impl IntoIterator<Item = &'a str>) -> String {
    let quoted: Vec<String> = values
        .into_iter()
        .map(|value| format!("{value:?}"))
        .collect();
    format!("[{}]", quoted.join(", "))
}
