//! Execution history type aliases.

use sqlbuild_cursor::algebra::models::LocalDateTime;

/// A UTC instant as its wall time with microsecond precision.
pub type UtcTime = LocalDateTime;
