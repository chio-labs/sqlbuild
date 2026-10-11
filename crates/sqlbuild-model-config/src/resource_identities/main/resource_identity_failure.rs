//! Python's `validate_resource_identity`: canonical lowercase snake_case resource identities.

use crate::header_metadata::constants::IDENTITY_HELP;
use crate::resource_identities::_helpers::spelling::{is_snake_case, suggested_identity};

/// The snake_case spelling to suggest for `name` and the rename help, or `None` when canonical.
pub fn resource_identity_failure(name: &str, private_identity: bool) -> Option<(String, String)> {
    let canonical = if private_identity {
        name.strip_prefix('_').is_some_and(is_snake_case)
    } else {
        is_snake_case(name)
    };
    if canonical {
        return None;
    }
    let suggestion = suggested_identity(name);
    let corrected = if private_identity {
        format!("_{suggestion}")
    } else {
        suggestion
    };
    Some((corrected, IDENTITY_HELP.to_owned()))
}
