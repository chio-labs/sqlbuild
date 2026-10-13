//! The progress line listing the dbt nodes still running.

use crate::dbt_events::constants::MAX_LISTED_ACTIVE_NODES;

fn elapsed(now: f64, started_at: f64) -> String {
    let seconds: i64 = ((now - started_at) as i64).max(0);
    if seconds == 0 {
        return "<1s".to_owned();
    }
    format!("{seconds}s")
}

/// The running count and the three longest-running nodes with their elapsed time.
#[must_use]
pub fn format_dbt_active_nodes(active_nodes: &[(String, f64)], now: f64) -> String {
    let mut ordered: Vec<&(String, f64)> = active_nodes.iter().collect();
    ordered.sort_by(|left, right| left.1.total_cmp(&right.1));
    let displayed: Vec<String> = ordered
        .iter()
        .take(MAX_LISTED_ACTIVE_NODES)
        .map(|(name, started_at)| format!("{name} {}", elapsed(now, *started_at)))
        .collect();
    let extra: usize = ordered.len() - displayed.len();
    let suffix: String = if extra > 0 {
        format!(", +{extra} more")
    } else {
        String::new()
    };
    let label: &str = if active_nodes.len() == 1 {
        "node"
    } else {
        "nodes"
    };
    format!(
        "running {} dbt {label}: {}{suffix}",
        active_nodes.len(),
        displayed.join(", ")
    )
}
