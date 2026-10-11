pub const API_VERSION: u32 = 1;
pub const NATIVE_BUILD_IDENTITY: &str = concat!(
    env!("CARGO_PKG_VERSION"),
    "+",
    env!("SQLBUILD_NATIVE_SOURCE_HASH")
);
pub(crate) const SCOPE_METADATA_SCHEMA_VERSION: u32 = 3;
pub(crate) const BUILT_IN_RULE_NAMESPACE: &str = "SQBR";
pub(crate) const PIPELINE_SUBJECT: &str = "pipeline";
pub(crate) const GENERIC_TEST_NAME: &str = "test";
pub(crate) const GENERIC_WORKS_NAME: &str = "works";
pub(crate) const GENERIC_BASIC_NAME: &str = "basic";
pub(crate) const GENERIC_SCENARIO_NAME: &str = "scenario";
pub(crate) const GENERIC_CASE_NAME: &str = "case";
pub(crate) const CUSTOM_RULE_NAMESPACE: &str = "XSQBR";
pub(crate) const REFERENCE_KIND: &str = "ref";
pub(crate) const MODEL_SCHEMA_CONFIG_KEY: &str = "schema";
pub(crate) const STAGING_LAYER_DIRECTORY: &str = "staging";
pub(crate) const INTERMEDIATE_LAYER_DIRECTORY: &str = "intermediate";
pub(crate) const MART_LAYER_DIRECTORY: &str = "mart";
pub(crate) const SOURCE_REFERENCE_KIND: &str = "source";
pub(crate) const VIEW_MATERIALIZATION: &str = "view";
pub(crate) const ENFORCED_CONTRACT: &str = "enforced";
pub(crate) const SELECT_STAR_MODEL_RULE_CODE: &str = "SQBRMODEL102";
pub(crate) const BOOLEAN_TYPE: &str = "BOOLEAN";
pub(crate) const DATE_TYPE: &str = "DATE";
pub(crate) const NEGATION_OPERATOR: &str = "-";
pub(crate) const DECLARATION_DOMAIN_COMPONENTS: usize = 3;
pub(crate) const RULE_CODE_NUMBER_LENGTH: usize = 3;
pub(crate) const EMPTY_FIXTURE_QUERY_TOKEN_COUNT: usize = 6;
pub(crate) const ENCLOSING_CTE_TOKEN_COUNT: usize = 3;
pub(crate) const PROJECT_CONFIG_FILE: &str = "sqlbuild_project.toml";
pub(crate) const SETTING_SNIPPET_INDENT: &str = "            ";
pub(crate) const NATIVE_ROWS_MEMO_VERSION: &str = "native-rules-rows-response-v1";
