use crate::check_command::models::{CheckGrouping, CheckResultText, CheckStatus};
use crate::json::models::JsonValue;

/// A check result with no message, metadata or warnings.
pub(super) fn result(name: &str, status: CheckStatus) -> CheckResultText {
    CheckResultText {
        name: name.to_owned(),
        status,
        severity: "error".to_owned(),
        message: None,
        error_message: None,
        metadata: JsonValue::Object(Vec::new()),
        warning_messages: Vec::new(),
    }
}

/// A grouping with dependencies and a declared group.
pub(super) fn grouping(dependencies: Option<&[&str]>, group: Option<&str>) -> CheckGrouping {
    CheckGrouping {
        dependencies: dependencies
            .map(|names| names.iter().map(|name| (*name).to_owned()).collect()),
        group: group.map(str::to_owned),
    }
}
