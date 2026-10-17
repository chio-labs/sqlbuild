//! The SQL rule result cache format and the inputs its keys separate.

/// Bumped whenever key derivation or the stored finding shape changes.
pub(crate) const CACHE_VERSION: &str = "sql-rules-v7";
pub(crate) const MODEL_KEY_KIND: &str = "model";
pub(crate) const FILE_KEY_KIND: &str = "file";
pub(crate) const LINT_KEY_KIND: &str = "lint";
pub(crate) const NO_CONTRACT: &str = "";
pub(crate) const MACRO_TOKEN: &str = "@";
pub(crate) const TEMPLATE_INTERPOLATION_START: &str = "${";
pub(crate) const VERSION_KEY: &str = "version";
pub(crate) const BUILD_IDENTITY_KEY: &str = "build_identity";
pub(crate) const ENTRIES_KEY: &str = "entries";
pub(crate) const IDENTITY_KEY: &str = "identity";
pub(crate) const FINDINGS_KEY: &str = "findings";
pub(crate) const TARGET_DIRECTORY: &str = "target";
pub(crate) const RULES_CACHE_DIRECTORY: &str = "rules-cache-native-v1";
pub(crate) const BULK_DIRECTORY: &str = "bulk";
