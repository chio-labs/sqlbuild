use polyglot_sql::ValidationSchema;
use polyglot_sql::expressions::Cte;
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CteUsageRequest {
    pub sql: String,
    pub dialect: String,
    #[serde(default)]
    pub schema: Option<ValidationSchema>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CteUsageBatch {
    pub requests: Vec<CteUsageRequest>,
}

#[derive(Debug)]
pub(crate) struct CteOutputSlot {
    pub name: String,
    pub read: bool,
    pub semantically_required: bool,
}

#[derive(Debug)]
pub(crate) struct CteSlotUsage {
    pub scope: String,
    pub name: String,
    pub original: Cte,
    pub slots: Vec<CteOutputSlot>,
    pub distinct: bool,
    pub set_operation: bool,
    pub model_output: bool,
}

#[derive(Debug, Serialize)]
pub(crate) struct CompactCteUsage {
    pub version: u32,
    pub strings: Vec<String>,
    pub ctes: Vec<(usize, usize, bool, bool, bool, bool)>,
    pub slots: Vec<(usize, usize, usize, bool, bool)>,
}
