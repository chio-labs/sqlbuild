//! Scenario marker callback and lexical failures.

use sqlbuild_sqltext::sql_scan::models::Unclosed;

/// Preserve the first callback or lexical failure in authored SQL order.
#[derive(Debug)]
pub enum MarkerError<E> {
    Scan(Unclosed),
    Resolve(E),
}
