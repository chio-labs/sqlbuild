//! Add to one compile metric.

use crate::compile_context::_helpers::active::active;

/// Add a non-negative metric value when a collector is active.
pub fn record_compile_metric(metric: &str, value: i64) {
    if let Some(collector) = active() {
        *collector
            .borrow_mut()
            .metrics
            .entry(metric.to_owned())
            .or_default() += u64::try_from(value).unwrap_or(0);
    }
}
