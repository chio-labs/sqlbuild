//! `@enum`/`@const` reference offsets scanned natively for the preview model loop.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_sqltext::compiler::main::declaration_references::scan_declaration_references;
use sqlbuild_sqltext::compiler::models::{
    DeclarationReference, DeclarationReferenceKind, DeclarationReferenceScan,
    DeclarationReferenceStop,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

/// `(kind code, name, member, start, end)`: kind 0 is an enum member, 1 a constant.
type ReferenceRow = (u8, String, Option<String>, usize, usize);
/// References and stop code: unclosed quote 0, block comment 1, invalid enum 2, constant 3.
type ScanRow = (Vec<ReferenceRow>, Option<u8>);

/// Return each SQL string's references and stopping error, or `None` where Python must expand it.
#[pyfunction]
fn scan_sql_declaration_references(
    py: Python<'_>,
    sqls: Vec<String>,
) -> PyResult<Vec<Option<ScanRow>>> {
    let scanned: Vec<Option<DeclarationReferenceScan>> = py
        .compiler_detach(|| Ok(scan_declaration_references(&sqls)))
        .map_err(compiler_error)?;
    Ok(scanned.into_iter().map(|scan| scan.map(scan_row)).collect())
}

fn scan_row(scan: DeclarationReferenceScan) -> ScanRow {
    (
        scan.references.into_iter().map(reference_row).collect(),
        scan.stop.map(|stop| match stop {
            DeclarationReferenceStop::UnclosedQuote => 0,
            DeclarationReferenceStop::UnclosedBlockComment => 1,
            DeclarationReferenceStop::Malformed(DeclarationReferenceKind::Enum) => 2,
            DeclarationReferenceStop::Malformed(DeclarationReferenceKind::Constant) => 3,
        }),
    )
}

fn reference_row(reference: DeclarationReference) -> ReferenceRow {
    let kind: u8 = match reference.kind {
        DeclarationReferenceKind::Enum => 0,
        DeclarationReferenceKind::Constant => 1,
    };
    (
        kind,
        reference.name,
        reference.member,
        reference.start,
        reference.end,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scan_sql_declaration_references, module)?)?;
    Ok(())
}
