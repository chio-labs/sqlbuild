//! The error for a target warehouse group under an adapter without session warehouses.

use crate::project::_helpers::help::{Setting, SettingValue, setting_note};

/// The message and help naming `[targets.<target>.warehouses] <group> = <value>` in `file_name`.
#[must_use]
pub fn unsupported_target_warehouse(
    (file_path, file_name): (&str, &str),
    adapter_name: &str,
    (target_name, group, value): (&str, &str, &str),
) -> (String, String) {
    let section: String = format!("targets.{target_name}.warehouses");
    let note: String = setting_note(&Setting {
        file_name,
        section: &section,
        key: group,
        value: SettingValue::Text(value),
    });
    (
        format!(
            "{file_path} [{section}] selects a {group} warehouse, but the '{adapter_name}' adapter has no warehouse to select; {note}"
        ),
        format!(
            "remove the [{section}] section from {file_name}; command-group warehouses need an adapter with a session warehouse, such as snowflake or an adapter extending it"
        ),
    )
}
