//! Outcomes of the native relationship-name and top-level CTE scans.

/// Which authored file kind a SQL text comes from, which names it in Python's messages.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RelationshipSource {
    /// A SQL test block.
    Test,
    /// A SQL scenario file.
    Scenario,
}

/// The expected-model names of one SQL text, or the error the scan raises.
#[derive(Debug, PartialEq, Eq)]
pub enum ExpectedNames {
    /// The `__expected__<model>` names in CTE order, exactly as Python extracts them.
    Scanned(Vec<String>),
    /// The message the extraction raises.
    Failed(String),
}

/// The top-level CTEs of one SQL text, or the scanner's error.
#[derive(Debug, PartialEq, Eq)]
pub enum TopLevelCtes {
    /// Each CTE's name and stripped body in authored order, exactly as Python's scanner reads them.
    Scanned(Vec<(String, String)>),
    /// The message the scanner raises.
    Failed(String),
}

/// One SQL test block a relationship fact is read from.
#[derive(Clone, Copy, Debug)]
pub struct TestBlockInput<'a> {
    /// The block's name, or its file's stem.
    pub name: &'a str,
    pub sql: &'a str,
    /// The block's `SqlTestMode` value.
    pub mode: &'a str,
}

/// One SQL test file, with the expected-model names a previous compile stored for it.
#[derive(Clone, Debug)]
pub struct TestFileInput<'a> {
    pub relative_path: &'a str,
    pub blocks: Vec<TestBlockInput<'a>>,
    /// Every block's names, reused instead of scanning the file again.
    pub stored: Option<Vec<Vec<String>>>,
}

/// One SQL scenario a relationship fact is read from.
#[derive(Clone, Copy, Debug)]
pub struct ScenarioInput<'a> {
    pub name: &'a str,
    pub relative_path: &'a str,
    pub sql: &'a str,
}

/// The facts of every test block and scenario that scanned, and the faults of the rest.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct RelationshipScan {
    /// Facts of tests, then scenarios, in authored order.
    pub facts: Vec<crate::scope_index::models::RelationshipFact>,
    /// `(relative path, message)` of each block or scenario that failed, tests first.
    pub faults: Vec<(String, String)>,
    /// Each unstored test file, by position, with every block's names when none failed.
    pub scanned_files: Vec<(usize, Vec<Vec<String>>)>,
}
