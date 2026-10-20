//! Whether an edited query still references only what the stored model read.

use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::ReferenceExtraction;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::header_changes::constants::{
    LINE_COMMENT, MODEL_KIND, REF_CALL, SEED_CALL, SEED_KIND, SOURCE_CALL, SOURCE_KIND,
};

/// Whether every model, source and seed `query_sql` names was among the stored `upstream`.
pub(crate) fn references_read(query_sql: &str, upstream: &[(String, String)]) -> bool {
    let syntax: LexicalSyntax = LexicalSyntax {
        line_comment_prefixes: vec![LINE_COMMENT.to_owned()],
        ..LexicalSyntax::default()
    };
    let ReferenceExtraction::Extracted(scan) = extract_sql_references(query_sql, &syntax) else {
        return false;
    };
    scan.references.iter().all(|reference| {
        let kind: Option<&str> = match reference.kind {
            REF_CALL => Some(MODEL_KIND),
            SOURCE_CALL => Some(SOURCE_KIND),
            SEED_CALL => Some(SEED_KIND),
            _ => None,
        };
        match (kind, &reference.package) {
            (Some(kind), None) => stored_upstream(upstream, kind, &reference.name),
            _ => true,
        }
    })
}

/// Whether `upstream` holds the `kind` resource `name`.
fn stored_upstream(upstream: &[(String, String)], kind: &str, name: &str) -> bool {
    upstream
        .iter()
        .any(|(stored_kind, stored_name)| stored_kind == kind && stored_name == name)
}
