//! The providers section of `sqb debug`.

use crate::debug_report::models::{DebugLine, DebugProvider, DebugStatus};

/// The provider count followed by one line per provider.
#[must_use]
pub fn debug_provider_lines(providers: &[DebugProvider]) -> Vec<DebugLine> {
    if providers.is_empty() {
        return vec![DebugLine::checked(
            "providers",
            "none discovered",
            (DebugStatus::Ok, None),
        )];
    }
    let mut lines: Vec<DebugLine> = vec![DebugLine::checked(
        "providers",
        &providers.len().to_string(),
        (DebugStatus::Ok, Some("discovered")),
    )];
    lines.extend(providers.iter().map(|provider| {
        DebugLine::checked(
            &provider.name,
            &format!("{}:{}", provider.relative_path, provider.class_name),
            (DebugStatus::Ok, Some("valid settings")),
        )
    }));
    lines
}
