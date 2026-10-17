//! The first config field, in Python's walk order, whose string holds a macro call.

use crate::config_presence::_helpers::macro_walk::walk_entries;
use crate::config_presence::models::MacroPath;
use crate::types::AuthoredNode;

/// Walk config values as `validate_no_macros_in_config_value` does, skipping the `skipped` keys.
pub fn first_macro_path<N: AuthoredNode>(values: &N, skipped: &[&str]) -> MacroPath {
    let mut entries = values.entries();
    entries.retain(|(key, _)| !skipped.iter().any(|name| key.is_text(name)));
    walk_entries(&entries, &[])
}
