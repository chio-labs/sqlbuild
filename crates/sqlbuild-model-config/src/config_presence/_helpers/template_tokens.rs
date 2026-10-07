//! Python's `TEMPLATE_OPEN_TOKEN in value` over one string.

use crate::config_presence::constants::TEMPLATE_OPEN_TOKEN;
use crate::config_presence::models::Presence;

/// Return whether `text` holds a template opening.
pub(crate) fn template_token(text: &str) -> Presence {
    if text.contains(TEMPLATE_OPEN_TOKEN) {
        Presence::Present
    } else {
        Presence::Absent
    }
}
