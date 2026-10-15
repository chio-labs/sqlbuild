//! `publishable_hook_name`: whether an operation's hook name is safe to publish.

use crate::lifecycle_events::_helpers::payloads::safe_hook_name;

/// Whether a hook name is an identifier of at most 128 characters.
#[must_use]
pub fn publishable_hook_name(name: &str) -> bool {
    safe_hook_name(name)
}
