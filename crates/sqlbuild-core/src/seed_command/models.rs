//! One finished seed as its progress row shows it.

/// A completed seed load.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SeedRow {
    pub name: String,
    pub ordinal: usize,
    pub total: usize,
    pub succeeded: bool,
    pub duration_ms: Option<f64>,
    pub error_message: Option<String>,
    pub error_code: Option<String>,
    pub error_help: Option<String>,
}
