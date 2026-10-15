//! `internal_logger`: whether a logger name belongs to SQLBuild.

use crate::diagnostic_routing::constants::{LOGGER_PREFIX, LOGGER_ROOT_NAME};

/// Whether `name` is the SQLBuild root logger or one of its children.
#[must_use]
pub fn internal_logger(name: &str) -> bool {
    name == LOGGER_ROOT_NAME || name.starts_with(LOGGER_PREFIX)
}
