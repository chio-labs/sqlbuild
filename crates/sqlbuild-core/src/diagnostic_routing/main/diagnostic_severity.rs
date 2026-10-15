//! `diagnostic_severity`: the diagnostic severity of a Python logging level.

use crate::diagnostic_routing::constants::{
    LEVEL_CRITICAL, LEVEL_ERROR, LEVEL_INFO, LEVEL_WARNING,
};

/// The severity name of logging level `level`.
#[must_use]
pub fn diagnostic_severity(level: i64) -> &'static str {
    if level >= LEVEL_CRITICAL {
        "critical"
    } else if level >= LEVEL_ERROR {
        "error"
    } else if level >= LEVEL_WARNING {
        "warning"
    } else if level >= LEVEL_INFO {
        "info"
    } else {
        "debug"
    }
}
