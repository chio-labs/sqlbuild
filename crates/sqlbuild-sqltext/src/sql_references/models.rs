//! Logical SQL references and the outcome of extracting them from one SQL text.

/// One `__ref`, `__source`, `__seed`, `__udf`, `__dbt_ref` or `__table_fn` call.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlReference {
    /// Python `SqlReferenceKind` value, such as `ref` or `table_fn`.
    pub kind: &'static str,
    pub name: String,
    pub package: Option<String>,
    /// Top-level arguments of a table function's call suffix; `None` for other kinds.
    pub call_argument_count: Option<usize>,
}

/// The references of one SQL text, Python's error for it, or a deferral to Python.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReferenceExtraction {
    /// Every reference in authored order, exactly as Python extracts them.
    Extracted(Vec<SqlReference>),
    /// The message of the `CompileInputError` Python raises for this text.
    Failed(String),
    /// A character or syntax rule the scan cannot classify exactly as Python does.
    Deferred,
}
