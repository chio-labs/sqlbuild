//! The stored entries of one SQL rule cache.

use std::collections::BTreeMap;

use crate::rule_cache::models::CachedEntry;

/// Every usable stored entry by project-relative path.
pub type CachedEntries = BTreeMap<String, CachedEntry>;
