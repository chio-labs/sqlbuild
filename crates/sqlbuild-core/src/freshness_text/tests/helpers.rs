use crate::freshness_text::models::{FreshnessSourceResult, FreshnessStatus};

/// An observed timestamp source with an age status.
pub(super) fn observed(
    name: &str,
    version: &str,
    age_status: Option<&str>,
) -> FreshnessSourceResult {
    FreshnessSourceResult {
        strategy: Some("sql".to_owned()),
        value_kind: Some("timestamp".to_owned()),
        current_data_version: Some(version.to_owned()),
        age_status: age_status.map(str::to_owned),
        ..FreshnessSourceResult::new(name, FreshnessStatus::Observed)
    }
}

/// A source with a status and message only.
pub(super) fn with_message(
    name: &str,
    status: FreshnessStatus,
    message: &str,
) -> FreshnessSourceResult {
    FreshnessSourceResult {
        message: Some(message.to_owned()),
        ..FreshnessSourceResult::new(name, status)
    }
}

/// Observed, unknown and error sources with every age status.
pub(super) fn mixed_results() -> Vec<FreshnessSourceResult> {
    vec![
        FreshnessSourceResult {
            lag_tolerance: Some("15m".to_owned()),
            ..observed("raw_orders", "2026-01-01T00:00:00", Some("warn"))
        },
        observed("raw_clicks", "2026-01-01T00:30:00", Some("pass")),
        observed("raw_shipments", "2025-12-31T20:00:00", Some("error")),
        observed("raw_inventory", "42", Some("unknown")),
        with_message(
            "raw_payments",
            FreshnessStatus::Unknown,
            "no freshness config and adapter metadata unavailable",
        ),
        with_message(
            "raw_events",
            FreshnessStatus::Error,
            "freshness query failed",
        ),
    ]
}

/// Results with one source per status.
pub(super) fn results_with(statuses: &[FreshnessStatus]) -> Vec<FreshnessSourceResult> {
    statuses
        .iter()
        .map(|status| FreshnessSourceResult::new("raw_orders", *status))
        .collect()
}
