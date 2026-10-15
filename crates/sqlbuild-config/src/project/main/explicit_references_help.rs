//! The help shown when explicit references reject an implicit reference.

use crate::project::_helpers::help::{Setting, SettingValue, current_value_note, setting_help};
use crate::project::constants::{ENFORCE_EXPLICIT_KEY, REFERENCES_SECTION};
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;

/// The current-value note, then help that relaxes the policy to allow `allowed`.
#[must_use]
pub fn explicit_references_help(allowed: &str) -> String {
    let setting = |value: bool| Setting {
        file_name: PROJECT_CONFIG_FILENAME,
        section: REFERENCES_SECTION,
        key: ENFORCE_EXPLICIT_KEY,
        value: SettingValue::Bool(value),
    };
    format!(
        "{}; {}",
        current_value_note(&setting(true)),
        setting_help(
            &format!("while migrating a project, to allow {allowed}"),
            &setting(false)
        )
    )
}
