//! Native TOML nesting limits.

/// The deepest container nesting a config file may use; deeper documents are rejected.
pub(crate) const MAX_CONTAINER_DEPTH: u32 = 64;
