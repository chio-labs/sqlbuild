use crate::compiled_project::models::{DeclarationSplice, SplicedSql};

/// `sql` with each scanned reference, in source order, replaced by its rendered text.
pub fn splice_declarations(sql: &str, splices: &[DeclarationSplice]) -> SplicedSql {
    crate::compiled_project::_helpers::splice::splice_declarations(sql, splices)
}
