//! Public compiler entry point for scanning `@enum`/`@const` references.

use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};

use crate::compiler::_helpers::declaration_references::scanner::scan_references;
use crate::compiler::models::DeclarationReference;

/// Each SQL string's declaration references in order, or None where Python must expand it.
#[must_use]
pub fn scan_declaration_references(sqls: &[String]) -> Vec<Option<Vec<DeclarationReference>>> {
    sqls.par_iter().map(|sql| scan_references(sql)).collect()
}
