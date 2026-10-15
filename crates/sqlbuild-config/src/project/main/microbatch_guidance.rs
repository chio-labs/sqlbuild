//! The note and help shown when microbatch concurrency is off.

use crate::project::_helpers::help::{Setting, SettingValue, current_value_note, setting_help};
use crate::project::constants::{MICROBATCH_CONCURRENCY_KEY, MICROBATCH_CONCURRENCY_PURPOSE};
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;
use sqlbuild_core::constants::SETTINGS_SECTION;

/// The current-value note and the help that enables microbatch concurrency.
#[must_use]
pub fn microbatch_guidance() -> (String, String) {
    let setting = |value: bool| Setting {
        file_name: PROJECT_CONFIG_FILENAME,
        section: SETTINGS_SECTION,
        key: MICROBATCH_CONCURRENCY_KEY,
        value: SettingValue::Bool(value),
    };
    (
        current_value_note(&setting(false)),
        setting_help(MICROBATCH_CONCURRENCY_PURPOSE, &setting(true)),
    )
}
