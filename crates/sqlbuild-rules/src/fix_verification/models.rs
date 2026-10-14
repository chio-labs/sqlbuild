use std::collections::BTreeMap;

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
