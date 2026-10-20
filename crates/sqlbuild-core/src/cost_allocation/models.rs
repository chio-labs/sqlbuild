//! Exact Python decimals, observed queries and their attributed run cost.

/// A finite non-negative Python `Decimal`: coefficient digits, most significant first, and exponent.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PyDecimal {
    pub digits: Vec<u8>,
    pub exponent: i64,
}

/// The warehouse identity whose busy time concurrent queries share.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct WarehouseKey {
    pub name: String,
    pub size: String,
    pub kind: Option<String>,
    pub cluster: Option<i64>,
}

/// One observed query; instants are microseconds on one consistent clock.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CostQuery {
    pub query_id: String,
    pub warehouse: WarehouseKey,
    pub started_micros: i128,
    pub completed_micros: i128,
    pub in_run: bool,
    pub resource_type: Option<String>,
    pub resource_name: Option<String>,
    pub bytes_scanned: i128,
}

/// The cost attributed to one resource on one warehouse (`ResourceCost`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceAllocation {
    pub resource_type: String,
    pub resource_name: String,
    pub warehouse: WarehouseKey,
    pub query_count: usize,
    pub attributed_seconds: PyDecimal,
    pub bytes_scanned: i128,
    pub estimated_compute_credits: PyDecimal,
    pub estimated_usd: PyDecimal,
}

/// Whether a run's queries were seen and fully priced.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AllocationStatus {
    Pending,
    Partial,
    Complete,
}

/// The run cost of the selected run's queries (`RunCostSummary` without its rate fields).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunAllocation {
    pub status: AllocationStatus,
    pub resources: Vec<ResourceAllocation>,
    pub query_count: usize,
    pub attributed_seconds: PyDecimal,
    pub bytes_scanned: i128,
    pub estimated_compute_credits: PyDecimal,
    pub estimated_usd: PyDecimal,
    pub limitations: Vec<String>,
}

/// One query-history read's window and the run whose CREATE text it requests by query tag.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct QueryHistoryWindow<'a> {
    pub database: Option<&'a str>,
    pub start: &'a str,
    pub end: Option<&'a str>,
    pub text_run_id: Option<&'a str>,
    pub result_limit: usize,
}
