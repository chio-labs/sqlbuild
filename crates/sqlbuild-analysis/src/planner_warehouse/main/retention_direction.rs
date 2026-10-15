//! Compare inspected retention with the desired days.

use crate::planner_warehouse::constants::{
    RETENTION_DECREASE, RETENTION_INCREASE, RETENTION_MATCH, RETENTION_MIXED,
};

/// Direction from the Delta retention values, or the effective days when none are set.
pub fn retention_direction(
    delta_values: [Option<i64>; 2],
    effective_days: i64,
    desired_days: i64,
) -> &'static str {
    let mut values: Vec<i64> = delta_values.into_iter().flatten().collect();
    if values.is_empty() {
        values.push(effective_days);
    }
    let increase = values.iter().any(|value| *value < desired_days);
    let decrease = values.iter().any(|value| *value > desired_days);
    match (increase, decrease) {
        (true, true) => RETENTION_MIXED,
        (true, false) => RETENTION_INCREASE,
        (false, true) => RETENTION_DECREASE,
        (false, false) => RETENTION_MATCH,
    }
}
