//! `ttl_mismatches`: tables whose stored TTL differs from the configured retention.

use crate::clickhouse::_helpers::digits::leading_number;
use crate::clickhouse::constants::{DAY_INTERVAL, SETTINGS_MARKER, TTL_MARKER};
use crate::clickhouse::models::TtlMismatch;
use crate::schema::constants::ALL_TABLES;
use crate::schema::main::table_spec::table_spec;

/// Each Recall table in `relations` (name, `CREATE` query) whose TTL keeps rows for other than `retention_days` plus the table's extra days.
#[must_use]
pub fn ttl_mismatches(relations: &[(String, String)], retention_days: u32) -> Vec<TtlMismatch> {
    let mut mismatches: Vec<TtlMismatch> = Vec::new();
    for table in ALL_TABLES {
        let spec = table_spec(table);
        let Some((_, query)) = relations.iter().find(|(name, _)| name == spec.name) else {
            continue;
        };
        let clause: Option<&str> = query
            .find(TTL_MARKER)
            .map(|start| &query[start + TTL_MARKER.len()..])
            .and_then(|clause| clause.split(SETTINGS_MARKER).next());
        let stored_days: Option<u64> = clause
            .and_then(|clause| {
                clause
                    .find(DAY_INTERVAL)
                    .map(|start| &clause[start + DAY_INTERVAL.len()..])
            })
            .and_then(leading_number);
        let configured_days: u64 = u64::from(retention_days.saturating_add(spec.ttl_extra_days));
        if stored_days != Some(configured_days) {
            mismatches.push(TtlMismatch {
                table: spec.name.to_owned(),
                stored_days,
                configured_days,
            });
        }
    }
    mismatches
}
