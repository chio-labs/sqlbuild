//! Cursor intrinsic calls replaced with the byte span of each replacement.

use crate::cursor_intrinsics::_helpers::scan::{
    CallScan, ScanStep, call_scan, contains_intrinsic_name, step,
};
use crate::cursor_intrinsics::models::IntrinsicSpan;
use crate::sql_lexing::main::unclosed_message::unclosed_message;

/// `sql` with each cursor intrinsic call replaced and each call's byte span, or the call's error.
pub(crate) fn replaced_with_spans(
    sql: &str,
    context: &str,
    replacement: impl Fn(&str) -> String,
) -> Result<(String, Vec<IntrinsicSpan>), String> {
    if !contains_intrinsic_name(sql) {
        return Ok((sql.to_owned(), Vec::new()));
    }
    let mut replaced: String = String::with_capacity(sql.len());
    let mut last: usize = 0;
    let mut spans: Vec<IntrinsicSpan> = Vec::new();
    let mut index: usize = 0;
    while index < sql.len() {
        let (name, end): (&str, usize) = match step(sql, index) {
            ScanStep::Next(next) => {
                index = next;
                continue;
            }
            ScanStep::Unclosed(construct) => return Err(unclosed_message(context, construct)),
            ScanStep::Intrinsic { name, end } => (name, end),
        };
        let close: usize = match call_scan(sql, end) {
            CallScan::Called(close) => close,
            CallScan::NotCalled => {
                return Err(format!("{context} intrinsic {name} must be called with ()"));
            }
            CallScan::Arguments => {
                return Err(format!(
                    "{context} intrinsic {name} does not accept arguments"
                ));
            }
            CallScan::Unclosed(construct) => {
                return Err(unclosed_message(
                    &format!("{context} cursor intrinsic"),
                    construct,
                ));
            }
        };
        replaced.push_str(&sql[last..index]);
        let output_start: usize = replaced.len();
        replaced.push_str(&replacement(name));
        spans.push(IntrinsicSpan {
            source_start: index,
            source_end: close + 1,
            output_start,
            output_end: replaced.len(),
        });
        last = close + 1;
        index = close + 1;
    }
    replaced.push_str(&sql[last..]);
    Ok((replaced, spans))
}
