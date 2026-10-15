//! Help that shows the exact setting to write.

use crate::project::_helpers::help::{Setting, SettingValue, setting_help};
use crate::project::models::{SettingSite, SettingText};

/// `<purpose>, set this in <file>:` followed by the exact TOML section and key.
#[must_use]
pub fn setting_help_text(purpose: &str, site: SettingSite<'_>, value: &SettingText) -> String {
    let value: SettingValue<'_> = match value {
        SettingText::Bool(flag) => SettingValue::Bool(*flag),
        SettingText::Integer(digits) => SettingValue::Integer(digits),
        SettingText::Text(text) => SettingValue::Text(text),
    };
    setting_help(
        purpose,
        &Setting {
            file_name: site.file_name,
            section: site.section,
            key: site.key,
            value,
        },
    )
}
