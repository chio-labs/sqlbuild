//! `lookup_rule_cache`: which paths' stored findings are still valid for their current keys.

use crate::rule_cache::models::CacheLookup;
use crate::rule_cache::types::CachedEntries;

/// Hits in key order of `keys`, with every path whose stored key differs or is absent missed.
#[must_use]
pub fn lookup_rule_cache(entries: &CachedEntries, keys: &[(String, String)]) -> CacheLookup {
    let mut lookup = CacheLookup::default();
    for (path, key) in keys {
        match entries.get(path) {
            Some(entry) if entry.identity == *key => {
                lookup.hits.push((path.clone(), entry.findings.clone()));
            }
            _ => lookup.misses.push(path.clone()),
        }
    }
    lookup
}
