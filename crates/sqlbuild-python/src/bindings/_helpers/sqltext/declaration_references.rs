//! `@enum`/`@const` reference offsets scanned natively for the model loop.

use sqlbuild_sqltext::compiler::main::declaration_references::scan_declaration_references;
use sqlbuild_sqltext::compiler::models::{
    DeclarationReference, DeclarationReferenceKind, DeclarationReferenceScan,
    DeclarationReferenceStop,
};

/// One natively scanned reference: kind 0 is an enum member, 1 a constant.
#[derive(Clone)]
pub(crate) struct ScannedReference {
    pub(crate) kind: u8,
    pub(crate) name: String,
    pub(crate) member: Option<String>,
    pub(crate) start: usize,
    pub(crate) end: usize,
}
/// References and stop code: unclosed quote 0, block comment 1, invalid enum 2, constant 3.
type ScanRow = (Vec<ScannedReference>, Option<u8>);

/// One SQL string's references and stop code, scanned without walking past malformed ones.
pub(crate) fn declaration_scan(sql: &str) -> ScanRow {
    let scanned: Vec<DeclarationReferenceScan> =
        scan_declaration_references(&[sql.to_owned()], false);
    scanned.into_iter().next().map(scan_row).unwrap_or_default()
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

fn reference_row(reference: DeclarationReference) -> ScannedReference {
    let kind: u8 = match reference.kind {
        DeclarationReferenceKind::Enum => 0,
        DeclarationReferenceKind::Constant => 1,
    };
    ScannedReference {
        kind,
        name: reference.name,
        member: reference.member,
        start: reference.start,
        end: reference.end,
    }
}
