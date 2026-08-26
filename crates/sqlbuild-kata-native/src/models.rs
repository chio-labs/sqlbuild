use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

use crate::constants::API_VERSION;

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct CacheConfig {
    pub enabled: bool,
    pub require_cacheable: bool,
}

impl CacheConfig {
    pub(crate) fn enabled_by_default() -> Self {
        Self {
            enabled: true,
            require_cacheable: false,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RuleException {
    pub rule: String,
    pub path: String,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RuleIgnore {
    pub rules: Vec<String>,
    pub paths: Vec<String>,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SelectStarAllow {
    pub paths: Vec<String>,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ThresholdOverride {
    pub paths: Vec<String>,
    pub thresholds: BTreeMap<String, u32>,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct KataConfig {
    pub select: Vec<String>,
    pub ignore: Vec<String>,
    pub thresholds: BTreeMap<String, u32>,
    pub threshold_overrides: Vec<ThresholdOverride>,
    pub rule_options: BTreeMap<String, BTreeMap<String, Value>>,
    pub rule_exceptions: Vec<RuleException>,
    pub rule_ignores: Vec<RuleIgnore>,
    pub select_star_allow: Vec<SelectStarAllow>,
    pub rule_paths: Vec<String>,
    pub rule_modules: Vec<String>,
    pub domains: Vec<String>,
    pub approved_source_tokens: Vec<String>,
    pub retired_source_tokens: BTreeMap<String, String>,
    pub cte_name_whitelist: Vec<String>,
    pub cte_name_denylist: Vec<String>,
    pub cache: CacheConfig,
}

impl Default for KataConfig {
    fn default() -> Self {
        Self {
            select: vec![],
            ignore: vec![],
            thresholds: BTreeMap::new(),
            threshold_overrides: vec![],
            rule_options: BTreeMap::new(),
            rule_exceptions: vec![],
            rule_ignores: vec![],
            select_star_allow: vec![],
            rule_paths: vec![],
            rule_modules: vec![],
            domains: vec![],
            approved_source_tokens: vec![],
            retired_source_tokens: BTreeMap::new(),
            cte_name_whitelist: vec![],
            cte_name_denylist: vec![],
            cache: CacheConfig::enabled_by_default(),
        }
    }
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct Reference {
    pub ref_kind: String,
    pub ref_name: String,
    pub ref_package: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct Column {
    pub name: String,
    #[serde(rename = "type", alias = "data_type")]
    pub data_type: String,
    pub nullable: Option<bool>,
    pub audit_count: u32,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct DeclarationMember {
    pub name: String,
    pub value: Value,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct Declaration {
    pub name: String,
    pub relative_path: String,
    pub members: Vec<DeclarationMember>,
    pub value: Option<Value>,
    pub value_type: Option<String>,
    pub render_as: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct Model {
    pub name: String,
    pub relative_path: String,
    pub query_sql: String,
    pub authored_sql: String,
    pub config: BTreeMap<String, Value>,
    pub references: Vec<Reference>,
    pub columns: Vec<Column>,
    pub enum_columns: Vec<String>,
    pub enum_declarations: Vec<Declaration>,
    pub constant_declarations: Vec<Declaration>,
    pub declared_audit_count: u32,
    pub targeting_test_count: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CustomRule {
    pub code: String,
    pub family: String,
    pub slug: String,
    pub message: String,
    pub remediation: String,
    #[serde(default)]
    pub enabled_by_default: bool,
    pub implementation_fingerprint: String,
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub source_line: u64,
    #[serde(default)]
    pub source_column: u64,
    #[serde(default)]
    pub owner: String,
    #[serde(default)]
    pub project_wide: bool,
    #[serde(default)]
    pub check_name: String,
    #[serde(default)]
    pub test_case_count: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Fault {
    pub code: String,
    pub path: String,
    pub line: u64,
    pub column: u64,
    pub message: String,
    pub remediation: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct EvaluateRequest {
    pub version: u32,
    pub project_dir: String,
    pub config: KataConfig,
    pub models: Vec<Model>,
    pub public_enums: Vec<Declaration>,
    pub public_constants: Vec<Declaration>,
    pub custom_rules: Vec<CustomRule>,
    pub custom_host: Option<CustomHostSpec>,
    pub project_fingerprint: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CustomHostSpec {
    pub program: String,
    pub arguments: Vec<String>,
    pub timeout_millis: u64,
    pub runtime_version: String,
    pub payload: Value,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ResolveRulesRequest {
    pub version: u32,
    pub config: KataConfig,
    pub custom_rules: Vec<CustomRule>,
}

impl Default for EvaluateRequest {
    fn default() -> Self {
        Self {
            version: API_VERSION,
            project_dir: ".".into(),
            config: KataConfig::default(),
            models: vec![],
            public_enums: vec![],
            public_constants: vec![],
            custom_rules: vec![],
            custom_host: None,
            project_fingerprint: None,
        }
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct EvaluateResponse {
    pub version: u32,
    pub faults: Vec<Fault>,
    pub evaluated_models: usize,
    pub cache_hits: usize,
    pub cache_misses: usize,
    pub ruleset_fingerprint: String,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct RuleGuidance {
    pub good_example: String,
    pub anti_tautology: String,
    pub mutation_check: String,
}

impl RuleGuidance {
    pub(crate) fn remediation(&self, introduction: &str) -> String {
        format!(
            "{introduction}\n\n{}\n\n{}\n\n{}",
            self.good_example, self.anti_tautology, self.mutation_check
        )
    }
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct RuleMetadata {
    pub code: String,
    pub family: String,
    pub slug: String,
    pub message: String,
    pub remediation: String,
    pub guidance: Option<RuleGuidance>,
    pub implementation_fingerprint: String,
    pub enabled_by_default: bool,
    pub project_wide: bool,
    pub custom: bool,
}

impl fensu_policy::policy::types::PolicyRule for RuleMetadata {
    type Applicability = ();

    fn code(&self) -> &str {
        &self.code
    }

    fn enabled_by_default(&self) -> bool {
        self.enabled_by_default
    }

    fn is_applicable(&self, _applicability: &Self::Applicability) -> bool {
        true
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct CatalogueResponse {
    pub version: u32,
    pub rules: Vec<RuleMetadata>,
}
