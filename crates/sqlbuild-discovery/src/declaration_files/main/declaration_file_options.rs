//! The options declaration discovery parses headers with.

use crate::_helpers::sorted_keys::sorted_keys;
use crate::constants::{SQL_AUDIT_HEADER_KEYS, SQL_FUNCTION_HEADER_KEYS, SQL_HOOK_HEADER_KEYS};
use crate::declaration_files::models::DeclarationFileOptions;

/// The header keys `FUNCTION`, `AUDIT` and `HOOK` statements accept.
#[must_use]
pub fn declaration_file_options() -> DeclarationFileOptions {
    DeclarationFileOptions {
        function_keys: sorted_keys(&SQL_FUNCTION_HEADER_KEYS),
        audit_keys: sorted_keys(&SQL_AUDIT_HEADER_KEYS),
        hook_keys: sorted_keys(&SQL_HOOK_HEADER_KEYS),
    }
}
