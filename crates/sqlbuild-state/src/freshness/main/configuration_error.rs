//! `configuration_error`: whether an observation failure is a source configuration error.

use crate::freshness::constants::{
    INCOMPLETE_CONFIGURATION_FRAGMENT, PHYSICAL_TABLE_SOURCE_FRAGMENT,
};

/// Configuration errors fail planning; every other observation failure marks the source unknown.
pub fn configuration_error(message: &str) -> bool {
    message.contains(PHYSICAL_TABLE_SOURCE_FRAGMENT)
        || message.contains(INCOMPLETE_CONFIGURATION_FRAGMENT)
}
