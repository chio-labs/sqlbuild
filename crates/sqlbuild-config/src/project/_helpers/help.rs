//! Help text naming an exact setting, and change-policy value checks.

use crate::models::ConfigValue;
use crate::project::_helpers::durations::parse_duration;
use crate::project::constants::{
    ADDITIONAL_HELP_SEPARATOR, BOUNDED_REPLAY_PREFIX, ON_SCHEMA_CHANGE_EXAMPLE,
    ON_SCHEMA_CHANGE_KEY, ON_SCHEMA_CHANGE_VALUES, REPLAY_ON_CHANGE_EXAMPLE,
    REPLAY_ON_CHANGE_VALUES, SETTING_SNIPPET_INDENT,
};
use crate::project::errors::ConfigFailure;

/// A setting value as TOML shows it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SettingValue<'a> {
    Bool(bool),
    Text(&'a str),
}

/// One setting: the file, section and key it lives at and the value to show.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Setting<'a> {
    pub(crate) file_name: &'a str,
    pub(crate) section: &'a str,
    pub(crate) key: &'a str,
    pub(crate) value: SettingValue<'a>,
}

fn toml_value(value: SettingValue<'_>) -> String {
    match value {
        SettingValue::Bool(true) => "true".to_owned(),
        SettingValue::Bool(false) => "false".to_owned(),
        SettingValue::Text(text) => {
            format!("\"{}\"", text.replace('\\', "\\\\").replace('"', "\\\""))
        }
    }
}

/// `setting_help`: `<purpose>, set this in <file>:` and the TOML section and key.
pub(crate) fn setting_help(purpose: &str, setting: &Setting<'_>) -> String {
    format!(
        "{purpose}, set this in {}:\n{SETTING_SNIPPET_INDENT}[{}]\n{SETTING_SNIPPET_INDENT}{} = {}",
        setting.file_name,
        setting.section,
        setting.key,
        toml_value(setting.value)
    )
}

/// `setting_note` for a value a file sets explicitly.
pub(crate) fn setting_note(setting: &Setting<'_>) -> String {
    format!(
        "{} sets [{}] {} = {}",
        setting.file_name,
        setting.section,
        setting.key,
        toml_value(setting.value)
    )
}

/// `join_helps`: one `= help:` label per paragraph.
pub(crate) fn join_helps(helps: &[String]) -> String {
    helps.join(ADDITIONAL_HELP_SEPARATOR)
}

fn valid_values(key: &str) -> String {
    if key == ON_SCHEMA_CHANGE_KEY {
        ON_SCHEMA_CHANGE_VALUES.join(", ")
    } else {
        REPLAY_ON_CHANGE_VALUES.join(", ")
    }
}

fn replay_problem(key: &str, value: &str) -> Result<Option<String>, ConfigFailure> {
    let Some(bounded) = value.strip_prefix(BOUNDED_REPLAY_PREFIX) else {
        return Ok(None);
    };
    let duration = str::trim(bounded);
    if parse_duration(duration)?.is_some() {
        return Ok(None);
    }
    Ok(Some(format!(
        "{key} '{value}' has an invalid duration '{duration}'; use a positive duration \
         such as 14d, 12h or 1mo"
    )))
}

/// `change_policy_problem`: why an `on_schema_change` or `replay_on_change` value is invalid.
pub(crate) fn change_policy_problem(
    key: &str,
    value: &ConfigValue,
) -> Result<Option<String>, ConfigFailure> {
    let valid = valid_values(key);
    let ConfigValue::String(text) = value else {
        return Ok(Some(format!(
            "{key} must be a string; valid values: {valid}"
        )));
    };
    if key == ON_SCHEMA_CHANGE_KEY && ON_SCHEMA_CHANGE_VALUES.contains(&text.as_str()) {
        return Ok(None);
    }
    if key != ON_SCHEMA_CHANGE_KEY && text.starts_with(BOUNDED_REPLAY_PREFIX) {
        return replay_problem(key, text);
    }
    if key != ON_SCHEMA_CHANGE_KEY && REPLAY_ON_CHANGE_VALUES[..2].contains(&text.as_str()) {
        return Ok(None);
    }
    Ok(Some(format!(
        "unknown {key} '{text}'; valid values: {valid}"
    )))
}

/// `change_policy_toml_help`: a valid TOML line for the change-policy key.
pub(crate) fn change_policy_toml_help(key: &str, file_name: &str, section: &str) -> String {
    let example = if key == ON_SCHEMA_CHANGE_KEY {
        ON_SCHEMA_CHANGE_EXAMPLE
    } else {
        REPLAY_ON_CHANGE_EXAMPLE
    };
    setting_help(
        &format!("use a valid {key}"),
        &Setting {
            file_name,
            section,
            key,
            value: SettingValue::Text(example),
        },
    )
}
