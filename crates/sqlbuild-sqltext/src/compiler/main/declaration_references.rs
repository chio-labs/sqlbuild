//! Public compiler entry point for scanning `@enum`/`@const` references.

use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};

use crate::compiler::_helpers::declaration_references::scanner::scan_references;
use crate::compiler::models::DeclarationReferenceScan;
use sqlbuild_core::text::models::PythonText;

/// Each SQL string's references and stopping error, with `python`'s word boundaries.
#[must_use]
pub fn scan_declaration_references(
    python: PythonText,
    sqls: &[String],
) -> Vec<DeclarationReferenceScan> {
    sqls.par_iter().map(|sql| scan_references(python, sql)).collect()
}
