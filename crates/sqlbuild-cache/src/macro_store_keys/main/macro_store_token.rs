//! `macro_store_token`: a macro named by its name, file, identity and exact source.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::models::JsonValue;

use crate::digest::main::content_digest::content_digest;
use crate::digest::main::hex_digest::hex_digest;
use crate::macro_store_keys::_helpers::key_text::key_text;

/// The key text of `[name, relative path, canonical identity, source digest]`, if storable.
pub fn macro_store_token(
    (name, relative_path): (JsonValue, JsonValue),
    identity: JsonValue,
    raw_source: &str,
) -> Result<Option<String>, JsonEmitError> {
    let source_digest: String = hex_digest(&content_digest(&[raw_source]));
    key_text(&JsonValue::Array(vec![
        name,
        relative_path,
        identity,
        JsonValue::String(source_digest),
    ]))
}
