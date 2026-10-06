//! Remediation text that shows the exact `sqlbuild_project.toml` setting to write.

use crate::constants::{PROJECT_CONFIG_FILE, SETTING_SNIPPET_INDENT};

/// `<purpose>, set this in sqlbuild_project.toml:` followed by the section and `key = value`.
pub(crate) fn setting_help(purpose: &str, section: &str, key: &str, value: &str) -> String {
    format!(
        "{purpose}, set this in {PROJECT_CONFIG_FILE}:\n{SETTING_SNIPPET_INDENT}[{section}]\n{SETTING_SNIPPET_INDENT}{key} = {value}"
    )
}
