//! The connection section of `sqb debug`.

use crate::debug_report::constants::{
    MASKED_VALUE, PREVIEW_CHARACTER_LIMIT, PREVIEW_EDGE_CHARACTERS, SECRET_CONNECTION_KEYS,
};
use crate::debug_report::models::{ConnectionCheck, ConnectionValue, DebugLine, DebugStatus};

fn displayed_value(key: &str, value: &ConnectionValue) -> String {
    if SECRET_CONNECTION_KEYS.contains(&key.to_lowercase().as_str()) {
        return MASKED_VALUE.to_owned();
    }
    let text: &str = match value {
        ConnectionValue::Null => return "null".to_owned(),
        ConnectionValue::Scalar(text) => return text.clone(),
        ConnectionValue::Text(text) => text,
    };
    let characters: Vec<char> = text.chars().collect();
    if characters.len() <= PREVIEW_CHARACTER_LIMIT {
        return text.to_owned();
    }
    let head: String = characters[..PREVIEW_EDGE_CHARACTERS].iter().collect();
    let tail: String = characters[characters.len() - PREVIEW_EDGE_CHARACTERS..]
        .iter()
        .collect();
    format!("{head}...{tail}")
}

fn check_lines(check: &ConnectionCheck) -> [DebugLine; 2] {
    let line = |label: &str, status: DebugStatus, message: &str| {
        DebugLine::checked(label, "", (status, Some(message)))
    };
    match check {
        ConnectionCheck::Skipped => [
            line(
                "connection test",
                DebugStatus::Skip,
                "skipped by --no-connection",
            ),
            line("query test", DebugStatus::Skip, "connection skipped"),
        ],
        ConnectionCheck::ConnectFailed(error) => [
            line("connection test", DebugStatus::Error, error),
            line("query test", DebugStatus::Skip, "connection failed"),
        ],
        ConnectionCheck::Connected { query_error } => [
            line("connection test", DebugStatus::Ok, "connected"),
            match query_error {
                Some(error) => line("query test", DebugStatus::Error, error),
                None => line("query test", DebugStatus::Ok, "SELECT 1"),
            },
        ],
    }
}

/// Connection settings sorted by key with secrets masked, then the connection checks.
#[must_use]
pub fn debug_connection_lines(
    settings: &[(String, ConnectionValue)],
    check: &ConnectionCheck,
) -> Vec<DebugLine> {
    let mut lines: Vec<DebugLine> = if settings.is_empty() {
        vec![DebugLine::checked(
            "settings",
            "no keys",
            (DebugStatus::Ok, None),
        )]
    } else {
        let mut sorted: Vec<&(String, ConnectionValue)> = settings.iter().collect();
        sorted.sort_by(|left, right| left.0.cmp(&right.0));
        sorted
            .into_iter()
            .map(|(key, value)| DebugLine::plain(key, &displayed_value(key, value)))
            .collect()
    };
    lines.extend(check_lines(check));
    lines
}
