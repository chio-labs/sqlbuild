//! Expression macro calls followed through the edits that move them, and their typed markers.

use polyglot_sql::expressions::{TYPED_EXPRESSION_FUNCTION, TYPED_LIKE_EXPRESSION_FUNCTION};

use crate::compiled_project::models::SplicedSpan;
use crate::sql_macros::_helpers::parsing::body::with_line_comment_closed;
use crate::sql_macros::models::{TextSplice, TypedCall};

/// `calls` moved `offset` bytes later.
pub(crate) fn shifted(calls: Vec<TypedCall>, offset: usize) -> impl Iterator<Item = TypedCall> {
    calls.into_iter().map(move |call| TypedCall {
        start: call.start + offset,
        end: call.end + offset,
        ..call
    })
}

/// Where byte `position` of the source lands, or `None` inside a replaced range.
fn spliced_position(position: usize, splices: &[TextSplice]) -> Option<usize> {
    let mut moved: isize = 0;
    for splice in splices {
        let (start, end) = splice.source;
        if end <= position {
            moved += (splice.output.1 - splice.output.0) as isize - (end - start) as isize;
        } else if start < position {
            return None;
        } else {
            break;
        }
    }
    let Ok(moved_position) = usize::try_from(position as isize + moved) else {
        return None;
    };
    Some(moved_position)
}

/// `calls` through `splices`, sorted and non-overlapping; a call a splice cuts into is dropped.
pub(crate) fn spliced(calls: Vec<TypedCall>, splices: &[TextSplice]) -> Vec<TypedCall> {
    if splices.is_empty() {
        return calls;
    }
    calls
        .into_iter()
        .filter_map(|call| {
            let start: usize = spliced_position(call.start, splices)?;
            let end: usize = spliced_position(call.end, splices)?;
            Some(TypedCall { start, end, ..call })
        })
        .collect()
}

/// Byte offset of each character offset of `text`, one past the end included.
fn byte_offsets(text: &str) -> Option<Vec<usize>> {
    if text.is_ascii() {
        return None;
    }
    let mut offsets: Vec<usize> = text.char_indices().map(|(offset, _)| offset).collect();
    offsets.push(text.len());
    Some(offsets)
}

/// Character-offset `spans` from `source` to `output` as byte splices.
pub(crate) fn byte_splices(source: &str, output: &str, spans: &[SplicedSpan]) -> Vec<TextSplice> {
    let (source_offsets, output_offsets) = (byte_offsets(source), byte_offsets(output));
    let byte = |offsets: &Option<Vec<usize>>, position: usize| match offsets {
        Some(offsets) => offsets.get(position).copied().unwrap_or(position),
        None => position,
    };
    spans
        .iter()
        .map(|span| TextSplice {
            source: (
                byte(&source_offsets, span.source_start),
                byte(&source_offsets, span.source_end),
            ),
            output: (
                byte(&output_offsets, span.output_start),
                byte(&output_offsets, span.output_end),
            ),
        })
        .collect()
}

/// One marker edit: the text inserted at a byte position, ordered among edits there.
struct MarkerEdit {
    position: usize,
    /// Closing edits come before opening ones at one position.
    opening: bool,
    /// Among openings, the outermost call first; among closings, the innermost first.
    order: (usize, usize),
    text: String,
}

/// `returns` as a SQL string literal.
fn quoted(returns: &str) -> String {
    format!("'{}'", returns.replace('\'', "''"))
}

/// `sql` with each call that declares `returns` wrapped in the typed marker, and each insertion.
pub(crate) fn typed_sql(sql: &str, calls: &[TypedCall]) -> (String, Vec<TextSplice>) {
    let mut edits: Vec<MarkerEdit> = Vec::new();
    for (index, call) in calls.iter().enumerate() {
        let (function, asserted): (&str, String) = match (&call.returns, &call.returns_like) {
            (Some(returns), _) => (TYPED_EXPRESSION_FUNCTION, quoted(returns)),
            (None, Some(like)) => (
                TYPED_LIKE_EXPRESSION_FUNCTION,
                with_line_comment_closed(like, true),
            ),
            (None, None) => continue,
        };
        let valid = |position: usize| position <= sql.len() && sql.is_char_boundary(position);
        if call.start >= call.end || !valid(call.start) || !valid(call.end) {
            continue;
        }
        let inner: &str = &sql[call.start..call.end];
        let line_break: &str = if with_line_comment_closed(inner, true).len() > inner.len() {
            "\n"
        } else {
            ""
        };
        edits.push(MarkerEdit {
            position: call.start,
            opening: true,
            order: (usize::MAX - call.end, usize::MAX - index),
            text: format!("{function}("),
        });
        edits.push(MarkerEdit {
            position: call.end,
            opening: false,
            order: (usize::MAX - call.start, index),
            text: format!("{line_break}, {asserted})"),
        });
    }
    if edits.is_empty() {
        return (sql.to_owned(), Vec::new());
    }
    edits.sort_by_key(|edit| (edit.position, edit.opening, edit.order));
    let mut typed: String = String::with_capacity(sql.len() + edits.len() * 16);
    let mut insertions: Vec<TextSplice> = Vec::with_capacity(edits.len());
    let mut cursor: usize = 0;
    for edit in edits {
        typed.push_str(&sql[cursor..edit.position]);
        cursor = edit.position;
        insertions.push(TextSplice {
            source: (edit.position, edit.position),
            output: (typed.len(), typed.len() + edit.text.len()),
        });
        typed.push_str(&edit.text);
    }
    typed.push_str(&sql[cursor..]);
    (typed, insertions)
}
