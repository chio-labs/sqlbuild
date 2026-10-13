//! The `sqb scope` options its text output reflects.

/// The command options a scope text rendering shows and repeats in follow-up commands.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ScopeTextRequest {
    pub target: Option<String>,
    pub at: Option<String>,
    pub as_path: Option<String>,
    pub defined_under: Option<String>,
    pub kinds: Vec<String>,
    pub glob: Option<String>,
    pub used_only: bool,
    pub include_nearby: bool,
    pub nearby_depth: i64,
    pub dependency_depth: i64,
    pub explain: Option<String>,
    pub globals: String,
    pub page_size: i64,
    pub paths: String,
    pub verbose: bool,
    pub no_cache: bool,
}
