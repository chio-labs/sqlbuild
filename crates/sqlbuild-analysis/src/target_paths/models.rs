//! The SQL test facts its target path is built from.

/// One SQL test or expanded case, as its target path needs it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlTestPathFacts {
    pub name: String,
    /// The authoring file, relative and in POSIX form.
    pub source_path: Option<String>,
    pub block_index: Option<i64>,
    pub case_name: Option<String>,
    /// The models of the test's chain, in any order and possibly repeated.
    pub model_names: Vec<String>,
}
