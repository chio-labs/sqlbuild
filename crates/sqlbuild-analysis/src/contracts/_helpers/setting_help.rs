//! Python's setting help texts (`sqlbuild.errors.setting_help`) for string settings.

use crate::contracts::constants::{ADDITIONAL_HELP_SEPARATOR, SETTING_SNIPPET_INDENT};

/// One string setting: the file it belongs to, its TOML section and key, and its value.
pub(crate) struct StringSetting<'a> {
    pub(crate) file_name: &'a str,
    pub(crate) section: &'a str,
    pub(crate) key: &'a str,
    pub(crate) value: &'a str,
}

/// A TOML string literal, as Python's `toml_value` renders a string.
pub(crate) fn toml_string(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

/// `<purpose>, set this in <file>:` followed by the indented section and key.
pub(crate) fn setting_help(purpose: &str, setting: &StringSetting<'_>) -> String {
    let StringSetting {
        file_name,
        section,
        key,
        value,
    } = setting;
    format!(
        "{purpose}, set this in {file_name}:\n{SETTING_SNIPPET_INDENT}[{section}]\n\
         {SETTING_SNIPPET_INDENT}{key} = {}",
        toml_string(value)
    )
}

/// A setting's current value, set explicitly or by default.
pub(crate) fn setting_note(setting: &StringSetting<'_>, explicit: bool) -> String {
    let StringSetting {
        file_name,
        section,
        key,
        value,
    } = setting;
    let rendered: String = toml_string(value);
    if explicit {
        format!("{file_name} sets [{section}] {key} = {rendered}")
    } else {
        format!("{file_name} does not set [{section}] {key}, so it defaults to {rendered}")
    }
}

/// `<purpose>, <target>:` followed by the exact lines to write, one per line.
pub(crate) fn snippet_help(purpose: &str, target: &str, lines: &[String]) -> String {
    let snippet: Vec<String> = lines
        .iter()
        .map(|line| format!("{SETTING_SNIPPET_INDENT}{line}"))
        .collect();
    format!("{purpose}, {target}:\n{}", snippet.join("\n"))
}

/// Several help paragraphs joined with one `= help:` label each.
pub(crate) fn join_helps(helps: &[String]) -> String {
    helps.join(ADDITIONAL_HELP_SEPARATOR)
}
