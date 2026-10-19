//! `plan_insert`: which rows of a batch still need writing, and which reuse a key with different content.

use crate::clickhouse::_helpers::planning::Planner;
use crate::clickhouse::models::{InsertPlan, StoredRow};
use crate::records::models::RecallRow;

/// Plan `rows` against what the store holds. An equal copy is delivered without writing; an artifact is written again only when its newest copy was seen before `refresh_before` (Recall timestamp text), so it outlives every reference. A key holding different content keeps the stored row, and a `recall_conflicts` row records the rejected digest.
#[must_use]
pub fn plan_insert(
    rows: Vec<RecallRow>,
    stored: &[StoredRow],
    (detected_at, refresh_before): (&str, &str),
) -> InsertPlan {
    let mut planner = Planner::new(stored, (detected_at, refresh_before));
    for row in rows {
        planner.add(row);
    }
    planner.finish()
}
