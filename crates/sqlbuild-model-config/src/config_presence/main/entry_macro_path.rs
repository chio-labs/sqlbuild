//! Where Python's config walk finds a macro call within one top-level config entry.

use crate::config_presence::_helpers::macro_walk::walk_entries;
use crate::config_presence::models::MacroPath;
use crate::types::AuthoredNode;

/// The first macro path `first_macro_path` reports for the single entry `key: value`.
pub fn entry_macro_path<N: AuthoredNode>(key: &N, value: &N) -> MacroPath {
    walk_entries(&[(key.clone(), value.clone())], &[])
}
