//! Python's `unsupported_keys_help`: nearest supported key suggestions.

/// The help for `keys` that are not among `supported_keys`.
pub fn unsupported_keys_help(keys: &[&str], supported_keys: &[String]) -> String {
    crate::_helpers::suggestions::unsupported_keys_help(keys, supported_keys)
}
