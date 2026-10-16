//! One statically found custom-rule test case and the import bindings of one test module.

/// One harness case: its file, CPython position and owning test.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct RuleTestEvidence {
    pub path: String,
    pub line: usize,
    pub column: usize,
    pub owner: String,
}

/// The rule a harness call must name: its importable module names and check function name.
#[derive(Debug)]
pub(crate) struct RuleTarget<'a> {
    pub(crate) modules: Vec<String>,
    pub(crate) check_name: &'a str,
}

/// An import outside the custom-rule allowlist: its statement's line and the module.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DisallowedImport {
    pub line: usize,
    pub module: String,
}

/// A source CPython's parser would reject.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct UnparsedSource;
