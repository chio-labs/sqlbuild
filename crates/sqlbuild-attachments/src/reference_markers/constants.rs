//! The reference calls that must be resolved before SQL executes, in reporting order.

/// `ref`, `seed`, `source`, `udf` and `table_fn` call prefixes.
pub(crate) const REFERENCE_CALL_PREFIXES: [&[u8]; 5] = [
    b"__ref(",
    b"__seed(",
    b"__source(",
    b"__udf(",
    b"__table_fn(",
];
