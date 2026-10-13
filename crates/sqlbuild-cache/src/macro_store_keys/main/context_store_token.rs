//! `context_store_token`: the digest of the whole context a macro may read.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::models::JsonValue;

use crate::digest::main::content_digest::content_digest;
use crate::digest::main::hex_digest::hex_digest;
use crate::macro_store_keys::_helpers::key_text::key_text;

/// The digest of the canonical context's key text, or `None` when it cannot be stored.
pub fn context_store_token(canonical: &JsonValue) -> Result<Option<String>, JsonEmitError> {
    Ok(key_text(canonical)?.map(|text| hex_digest(&content_digest(&[text]))))
}
