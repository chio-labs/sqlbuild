//! The `values` CPython gives an f-string's `JoinedStr` or a t-string's `TemplateStr`.

use ruff_python_ast::{Expr, FStringPart};

use crate::cpython_tree::_helpers::joined::{JoinedPiece, element_pieces, merged_values};
use crate::cpython_tree::models::CpythonNode;

/// The merged constants and interpolations of an f-string or t-string; empty for other nodes.
pub(crate) fn joined_values(expression: &Expr) -> Vec<CpythonNode<'_>> {
    let pieces: Vec<JoinedPiece<'_>> = match expression {
        Expr::FString(fstring) => fstring
            .value
            .iter()
            .flat_map(|part| match part {
                FStringPart::Literal(literal) => {
                    vec![JoinedPiece::Text(&literal.value, literal.range.start())]
                }
                FStringPart::FString(part) => element_pieces(&part.elements),
            })
            .collect(),
        Expr::TString(tstring) => tstring
            .value
            .iter()
            .flat_map(|part| element_pieces(&part.elements))
            .collect(),
        _ => Vec::new(),
    };
    merged_values(pieces)
}
