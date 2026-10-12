//! CPython's merging of adjacent string pieces in f-strings, t-strings and format specs.

use ruff_python_ast::{InterpolatedStringElement, InterpolatedStringElements};
use ruff_text_size::{TextLen, TextSize};

use crate::cpython_tree::models::{CpythonNode, TextConstant};

/// One piece CPython concatenates: literal text at an offset, or an interpolation.
pub(crate) enum JoinedPiece<'a> {
    Text(&'a str, TextSize),
    Interpolation(&'a ruff_python_ast::InterpolatedElement),
}

/// The pieces of f-string elements; a self-documenting `{x=}` contributes its text first.
pub(crate) fn element_pieces(elements: &InterpolatedStringElements) -> Vec<JoinedPiece<'_>> {
    elements.iter().flat_map(pieces).collect()
}

fn pieces(element: &InterpolatedStringElement) -> Vec<JoinedPiece<'_>> {
    match element {
        InterpolatedStringElement::Literal(literal) => {
            vec![JoinedPiece::Text(&literal.value, literal.range.start())]
        }
        InterpolatedStringElement::Interpolation(interpolation) => {
            let after_brace: TextSize = interpolation.range.start() + '{'.text_len();
            let debug: Option<JoinedPiece<'_>> = interpolation
                .debug_text
                .as_ref()
                .map(|debug_text| JoinedPiece::Text(debug_text.as_str(), after_brace));
            debug
                .into_iter()
                .chain([JoinedPiece::Interpolation(interpolation)])
                .collect()
        }
    }
}

/// Merge runs of text into constants located at the run's first piece, dropping empty runs.
pub(crate) fn merged_values(pieces: Vec<JoinedPiece<'_>>) -> Vec<CpythonNode<'_>> {
    let mut values: Vec<CpythonNode<'_>> = Vec::new();
    let mut run: Option<TextConstant> = None;
    for piece in pieces {
        match piece {
            JoinedPiece::Text(text, start) => {
                let constant: &mut TextConstant = run.get_or_insert_with(|| TextConstant {
                    value: String::new(),
                    start,
                });
                constant.value.push_str(text);
            }
            JoinedPiece::Interpolation(interpolation) => {
                values.extend(non_empty(run.take()));
                values.push(CpythonNode::Interpolation(interpolation));
            }
        }
    }
    values.extend(non_empty(run));
    values
}

fn non_empty<'a>(run: Option<TextConstant>) -> Option<CpythonNode<'a>> {
    run.filter(|constant| !constant.value.is_empty())
        .map(CpythonNode::Text)
}
