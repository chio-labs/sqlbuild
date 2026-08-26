use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

use crate::constants::{API_VERSION, SCOPE_METADATA_SCHEMA_VERSION};

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
pub(crate) struct SqlTestPolicyConfig {
    pub pipeline_directory: String,
}

impl Default for SqlTestPolicyConfig {
    fn default() -> Self {
        Self {
            pipeline_directory: "pipelines".into(),
        }
    }
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
    pub sql_tests: SqlTestPolicyConfig,
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
            sql_tests: SqlTestPolicyConfig::default(),
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

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum ResourceKind {
    Model,
    Test,
    Scenario,
    Hook,
    Function,
    Audit,
    Source,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum DeclarationKind {
    Macro,
    Enum,
    Constant,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum ScopeKind {
    Global,
    Inherited,
    Local,
    Private,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum UsageKind {
    Runtime,
    Generated,
    DeclarationDependency,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum GrantKind {
    ExpectedModel,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum VisibilityReason {
    Global,
    InheritedAncestor,
    LocalOwner,
    PrivateOwner,
    ExpectedModel,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum InaccessibleReason {
    LocalBoundary,
    SiblingScope,
    DescendantScope,
    UnrelatedScope,
    PrivateOwner,
    UnsupportedResourceKind,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum DiagnosticSeverity {
    Error,
    Warning,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub(crate) enum ScopeDiagnosticCode {
    S001,
    S002,
    S003,
    S004,
    S005,
    S006,
    S007,
    S008,
    S009,
    S010,
    S011,
    S012,
    S013,
    S014,
    S015,
    S016,
    S017,
    S018,
    S019,
    S020,
    S021,
    S022,
    S023,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeOwnershipRoot {
    pub path: String,
    pub resource_kind: Option<ResourceKind>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeResource {
    pub identity: String,
    pub kind: ResourceKind,
    pub name: String,
    pub path: String,
    pub ownership_root: String,
    pub ownership_root_kind: Option<ResourceKind>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeMacroMetadata {
    pub parameters: Vec<String>,
    pub dependencies: Vec<String>,
    pub source_digest: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeEnumMember {
    pub name: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeEnumMetadata {
    pub members: Vec<ScopeEnumMember>,
    pub scalar_type: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeConstantMetadata {
    pub logical_type: String,
    pub collection_kind: Option<String>,
    pub item_count: Option<u64>,
    pub nullable: bool,
    pub render_as: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct ScopeDeclarationMetadata {
    pub r#macro: Option<ScopeMacroMetadata>,
    pub r#enum: Option<ScopeEnumMetadata>,
    pub constant: Option<ScopeConstantMetadata>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeDeclaration {
    pub identity: String,
    pub kind: DeclarationKind,
    pub name: String,
    pub owner: Option<String>,
    pub path: String,
    pub line: u64,
    pub column: u64,
    pub scope: ScopeKind,
    pub ownership_root: String,
    pub owning_path: Option<String>,
    pub metadata: ScopeDeclarationMetadata,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeUsage {
    pub consumer: String,
    pub declaration: String,
    pub kind: UsageKind,
    pub through: Option<String>,
    pub enum_member: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeGrant {
    pub resource: String,
    pub declaration: String,
    pub through: String,
    pub kind: GrantKind,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeVisibility {
    pub resource: String,
    pub declaration: String,
    pub reason: VisibilityReason,
    pub through: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeInaccessible {
    pub resource: String,
    pub declaration: String,
    pub reason: InaccessibleReason,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeDiagnostic {
    pub code: ScopeDiagnosticCode,
    pub message: String,
    pub severity: DiagnosticSeverity,
    pub path: Option<String>,
    pub line: Option<u64>,
    pub column: Option<u64>,
    pub declaration: Option<String>,
    pub resource: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeCompleteness {
    pub discovery: bool,
    pub static_visibility: bool,
    pub runtime_usage: bool,
    pub relationships: bool,
    pub placement: bool,
    pub promotion_impact: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ScopeIndexFacts {
    #[serde(deserialize_with = "crate::scope_metadata::deserialize_scope_schema_version")]
    pub schema_version: u32,
    pub ownership_roots: Vec<ScopeOwnershipRoot>,
    pub resources: Vec<ScopeResource>,
    pub declarations: Vec<ScopeDeclaration>,
    pub usages: Vec<ScopeUsage>,
    pub grants: Vec<ScopeGrant>,
    pub visibility: Vec<ScopeVisibility>,
    pub inaccessible: Vec<ScopeInaccessible>,
    pub diagnostics: Vec<ScopeDiagnostic>,
    pub complete: bool,
    pub completeness: ScopeCompleteness,
}

impl Default for ScopeIndexFacts {
    fn default() -> Self {
        Self {
            schema_version: SCOPE_METADATA_SCHEMA_VERSION,
            ownership_roots: vec![],
            resources: vec![],
            declarations: vec![],
            usages: vec![],
            grants: vec![],
            visibility: vec![],
            inaccessible: vec![],
            diagnostics: vec![],
            complete: false,
            completeness: ScopeCompleteness {
                discovery: false,
                static_visibility: false,
                runtime_usage: false,
                relationships: false,
                placement: false,
                promotion_impact: false,
            },
        }
    }
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
#[serde(rename_all = "snake_case")]
pub(crate) enum SqlTestMode {
    Model,
    Macro,
    Udf,
    TableFn,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum DirectTestResourceKind {
    Macro,
    Udf,
    TableFn,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TestedResource {
    pub kind: DirectTestResourceKind,
    pub name: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SqlTestParameterFact {
    pub name: String,
    #[serde(rename = "type")]
    pub value_type: String,
    pub nullable: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SqlTestParameterValueFact {
    pub name: String,
    #[serde(rename = "type")]
    pub value_type: String,
    pub value: serde_json::Value,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SqlTestFact {
    pub source_path: String,
    pub ownership_root: String,
    pub block_index: u64,
    pub name: String,
    pub explicit_name: Option<String>,
    #[serde(default)]
    pub parent_name: Option<String>,
    #[serde(default)]
    pub case_name: Option<String>,
    #[serde(default)]
    pub case_index: Option<u64>,
    #[serde(default)]
    pub case_fingerprint: Option<String>,
    #[serde(default)]
    pub parameter_schema: Vec<SqlTestParameterFact>,
    #[serde(default)]
    pub parameters: Vec<SqlTestParameterValueFact>,
    pub mode: SqlTestMode,
    pub expected_model_names: Vec<String>,
    pub assertion_names: Vec<String>,
    pub assertion_target_model_names: Vec<String>,
    pub target_model_names: Vec<String>,
    pub tested_resources: Vec<TestedResource>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SqlScenarioFact {
    pub source_path: String,
    pub ownership_root: String,
    pub name: String,
    pub description: Option<String>,
    pub expected_model_names: Vec<String>,
    pub assertion_names: Vec<String>,
    pub assertion_target_model_names: Vec<String>,
    pub target_model_names: Vec<String>,
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
    pub sql_tests: Vec<SqlTestFact>,
    pub sql_scenarios: Vec<SqlScenarioFact>,
    pub public_enums: Vec<Declaration>,
    pub public_constants: Vec<Declaration>,
    pub scope_index: ScopeIndexFacts,
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
            sql_tests: vec![],
            sql_scenarios: vec![],
            public_enums: vec![],
            public_constants: vec![],
            scope_index: ScopeIndexFacts::default(),
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
