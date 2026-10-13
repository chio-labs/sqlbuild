//! The detail text after each source name.

use crate::cli_text::models::CliStyle;
use crate::freshness_text::models::{FreshnessSourceResult, FreshnessStatus};

fn muted_part(style: CliStyle, (label, value): (&str, Option<&String>)) -> Option<String> {
    value.map(|value| style.muted(&format!("{label} {value}")))
}

/// The detail text of one source line.
pub(crate) fn detail(result: &FreshnessSourceResult, style: CliStyle) -> String {
    let mut parts: Vec<String> = Vec::new();
    match result.status {
        FreshnessStatus::Observed => {
            parts.extend(muted_part(
                style,
                ("value", result.current_data_version.as_ref()),
            ));
            parts.extend(muted_part(style, ("kind", result.value_kind.as_ref())));
            parts.extend(muted_part(style, ("via", result.strategy.as_ref())));
        }
        FreshnessStatus::Changed | FreshnessStatus::Unchanged | FreshnessStatus::Tolerated => {
            parts.extend(muted_part(
                style,
                ("previous", result.previous_data_version.as_ref()),
            ));
            parts.extend(muted_part(
                style,
                ("current", result.current_data_version.as_ref()),
            ));
        }
        FreshnessStatus::Error => {
            return result
                .message
                .as_deref()
                .map_or_else(String::new, |message| style.error(message));
        }
        FreshnessStatus::Unknown => {
            return result
                .message
                .as_deref()
                .map_or_else(String::new, |message| style.warning(message));
        }
    }
    parts.extend(muted_part(
        style,
        ("tolerance", result.lag_tolerance.as_ref()),
    ));
    if let Some(age) = &result.age_status {
        parts.push(style.status_text(age, &format!("age {age}")));
    }
    parts.join("  ")
}
