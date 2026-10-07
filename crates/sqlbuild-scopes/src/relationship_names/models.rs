//! Outcomes of the native relationship-name scan.

/// The expected-model names of one SQL text, or a deferral to Python's extraction.
#[derive(Debug, PartialEq, Eq)]
pub enum ExpectedNames {
    /// The `__expected__<model>` names in CTE order, exactly as Python extracts them.
    Scanned(Vec<String>),
    /// Python raises for this text, or classifies a character the scan reached differently.
    Deferred,
}
