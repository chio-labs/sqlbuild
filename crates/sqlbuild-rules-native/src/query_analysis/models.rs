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

#[derive(Debug)]
pub(crate) struct CteBindingOptions<'a> {
    pub schema: Option<&'a polyglot_sql::ValidationSchema>,
    pub dialect: polyglot_sql::DialectType,
    pub quoted_ignore_case: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CteUsageBatch {
    pub requests: Vec<CteUsageRequest>,
}

#[derive(Debug)]
pub(crate) struct CteOutputSlot {
    pub locally_read: bool,
    pub name: String,
    pub read: bool,
    pub semantically_required: bool,
}

#[derive(Debug)]
pub(crate) struct CteSlotUsage {
    pub partially_checked: bool,
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
    pub local_reads: Vec<(usize, usize)>,
    pub partial_ctes: Vec<usize>,
    pub version: u32,
    pub strings: Vec<String>,
    pub ctes: Vec<(usize, usize, bool, bool, bool, bool)>,
    pub slots: Vec<(usize, usize, usize, bool, bool)>,
}
