use crate::compiled_project::constants::HEADER_METADATA_KEYS;

/// Whether `key` is header metadata, attached as schema and stripped from the model's config.
pub fn is_header_metadata_key(key: &str) -> bool {
    HEADER_METADATA_KEYS.contains(&key)
}
