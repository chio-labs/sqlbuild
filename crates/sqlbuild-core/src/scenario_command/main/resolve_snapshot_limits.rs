//! Effective snapshot capture limits.

use crate::scenario_command::constants::{
    DEFAULT_MAX_SNAPSHOT_BYTES_PER_RELATION, DEFAULT_MAX_SNAPSHOT_ROWS_PER_RELATION,
    DEFAULT_MAX_SNAPSHOT_TOTAL_BYTES, DEFAULT_MAX_SNAPSHOT_TOTAL_ROWS,
};
use crate::scenario_command::models::{SnapshotLimitConfig, SnapshotLimitInputs, SnapshotLimits};

/// Each limit from the command line, else the configuration, else its default.
#[must_use]
pub fn resolve_snapshot_limits(
    inputs: SnapshotLimitInputs,
    config: SnapshotLimitConfig,
) -> SnapshotLimits {
    SnapshotLimits {
        max_rows_per_relation: inputs
            .max_rows_per_relation
            .or(config.max_rows_per_relation)
            .unwrap_or(DEFAULT_MAX_SNAPSHOT_ROWS_PER_RELATION),
        max_total_rows: inputs
            .max_total_rows
            .or(config.max_total_rows)
            .unwrap_or(DEFAULT_MAX_SNAPSHOT_TOTAL_ROWS),
        max_bytes_per_relation: inputs
            .max_bytes_per_relation
            .or(config.max_bytes_per_relation)
            .unwrap_or(DEFAULT_MAX_SNAPSHOT_BYTES_PER_RELATION),
        max_total_bytes: inputs
            .max_total_bytes
            .or(config.max_total_bytes)
            .unwrap_or(DEFAULT_MAX_SNAPSHOT_TOTAL_BYTES),
        force: inputs.force,
    }
}
