use std::collections::BTreeMap;

/// Proof requirements for a proposed automatic rule fix.
#[derive(Debug)]
pub struct FixEligibility {
    pub model_body: bool,
    pub has_fix: bool,
    pub safe_code: bool,
    pub conditionless_join: bool,
    pub snowflake: bool,
}

/// One authored edit measured in Unicode character offsets.
#[derive(Debug)]
pub struct FixEdit {
    pub start: usize,
    pub end: usize,
    pub replacement: String,
}

/// Equality facts extracted from compiler-owned Python views.
#[derive(Debug)]
pub struct ModelComparison {
    pub owner: usize,
    pub edited: bool,
    pub columns_known: bool,
    pub columns_equal: bool,
    pub dependencies_equal: bool,
    pub lineage_equal: bool,
}

/// Location-insensitive diagnostic multiplicities for one owner.
#[derive(Debug)]
pub struct DiagnosticComparison {
    pub owner: usize,
    pub edited: bool,
    pub before: BTreeMap<(String, String, String, String), i64>,
    pub after: BTreeMap<(String, String, String, String), i64>,
}

/// Failures attributed to edited owners and changes outside those owners.
#[derive(Debug, Default)]
pub struct FixComparisonResult {
    pub failing: BTreeMap<usize, String>,
    pub unattributed: bool,
}
