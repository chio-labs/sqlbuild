//! The note and help shown when SQL analysis is turned off.

use crate::project::_helpers::help::{Setting, SettingValue, setting_help, setting_note};
use crate::project::constants::{LOCAL_CONFIG_FILENAME, SQL_ANALYSIS_KEY};
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;
use sqlbuild_core::constants::SETTINGS_SECTION;

/// The note naming the file that turns SQL analysis off and the help that turns it on for `purpose`.
#[must_use]
pub fn sql_analysis_off_guidance(local_override: bool, purpose: &str) -> (String, String) {
    let file_name: &str = if local_override {
        LOCAL_CONFIG_FILENAME
    } else {
        PROJECT_CONFIG_FILENAME
    };
    let setting = |value: bool| Setting {
        file_name,
        section: SETTINGS_SECTION,
        key: SQL_ANALYSIS_KEY,
        value: SettingValue::Bool(value),
    };
    (
        setting_note(&setting(false)),
        setting_help(purpose, &setting(true)),
    )
}
