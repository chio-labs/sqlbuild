//! Python check results as the command renders them.

use crate::json::models::JsonValue;

/// How one check ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CheckStatus {
    Pass,
    Warn,
    Fail,
}

impl CheckStatus {
    /// The label rows and the summary use.
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Pass => "PASS",
            Self::Warn => "WARN",
            Self::Fail => "FAIL",
        }
    }

    /// The status JSON output spells.
    #[must_use]
    pub fn value(self) -> &'static str {
        match self {
            Self::Pass => "pass",
            Self::Warn => "warn",
            Self::Fail => "fail",
        }
    }
}

/// One executed Python check.
#[derive(Clone, Debug, PartialEq)]
pub struct CheckResultText {
    pub name: String,
    pub status: CheckStatus,
    /// The `CheckSeverity` value.
    pub severity: String,
    pub message: Option<String>,
    pub error_message: Option<String>,
    pub metadata: JsonValue,
    pub warning_messages: Vec<String>,
}

/// What decides a check's output group: its dependencies and declared group.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CheckGrouping {
    /// Python dependency names, then SQL dependency names; `None` without a Python graph.
    pub dependencies: Option<Vec<String>>,
    pub group: Option<String>,
}

/// One rendered row: the result and the duration the progress projector recorded.
#[derive(Clone, Debug, PartialEq)]
pub struct CheckRow {
    pub result: CheckResultText,
    pub duration_ms: Option<f64>,
}
