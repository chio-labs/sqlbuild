//! Outcomes of the native relationship-name and top-level CTE scans.

/// Which authored file kind a SQL text comes from, which names it in Python's messages.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RelationshipSource {
    /// A SQL test block.
    Test,
    /// A SQL scenario file.
    Scenario,
}

/// The expected-model names of one SQL text, Python's error, or a deferral to Python.
#[derive(Debug, PartialEq, Eq)]
pub enum ExpectedNames {
    /// The `__expected__<model>` names in CTE order, exactly as Python extracts them.
    Scanned(Vec<String>),
    /// The message Python's extraction raises.
    Failed(String),
    /// Python classifies a character the scan reached differently.
    Deferred,
}

/// The top-level CTEs of one SQL text, Python's scanner error, or a deferral to Python.
#[derive(Debug, PartialEq, Eq)]
pub enum TopLevelCtes {
    /// Each CTE's name and stripped body in authored order, exactly as Python's scanner reads them.
    Scanned(Vec<(String, String)>),
    /// The message Python's scanner raises.
    Failed(String),
    /// Python classifies a character the scan reached differently.
    Deferred,
}
