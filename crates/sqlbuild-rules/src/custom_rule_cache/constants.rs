//! The custom-rule result cache format and the inputs its identities separate.

/// Bumped whenever identity derivation or the stored entry shape changes.
pub(crate) const CACHE_VERSION: &str = "custom-rules-native-v2";
pub(crate) const RULE_KIND: &str = "rule";
pub(crate) const PROJECT_SUBJECT_KIND: &str = "project";
pub(crate) const MODEL_SUBJECT_KIND: &str = "model";
/// The subject key of a project-wide rule's single invocation.
pub(crate) const PROJECT_SUBJECT: &str = "";
pub(crate) const PROJECT_SUBJECT_NAME: &str = "project";
pub(crate) const MODEL_SUBJECT_NAME: &str = "model";
pub(crate) const VERSION_KEY: &str = "version";
pub(crate) const RULES_KEY: &str = "rules";
pub(crate) const IDENTITY_KEY: &str = "identity";
pub(crate) const READSETS_KEY: &str = "readsets";
pub(crate) const ENTRIES_KEY: &str = "entries";
pub(crate) const CODE_KEY: &str = "code";
pub(crate) const PATH_KEY: &str = "path";
