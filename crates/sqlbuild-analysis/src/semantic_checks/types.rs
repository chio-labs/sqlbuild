//! Row aliases shared by the semantic completion entries and their callers.

use crate::semantic_checks::models::{CompletedDiagnostic, FinalDiagnostic};

/// One revalidated binding row: `(code, start, end)`.
pub type RevisedBinding = (String, Option<i64>, Option<i64>);

/// A completed outcome's diagnostics, model binding positions and final order.
pub type CompletedParts = (
    Vec<CompletedDiagnostic>,
    Option<Vec<Vec<usize>>>,
    Vec<FinalDiagnostic>,
);
