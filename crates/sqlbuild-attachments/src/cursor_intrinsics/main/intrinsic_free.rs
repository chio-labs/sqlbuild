//! Python's `reject_cursor_intrinsics`, with the error it raises.

use crate::cursor_intrinsics::_helpers::scan::{
    CallScan, ScanStep, call_scan, contains_intrinsic_name, step,
};
use crate::cursor_intrinsics::models::IntrinsicCheck;
use crate::sql_lexing::main::unclosed_message::unclosed_message;
use sqlbuild_sqltext::sql_scan::models::Unclosed;

/// Python's acceptance of `sql`, its error for `context`, or `Deferred` where only Python decides.
#[must_use]
pub fn intrinsic_free(sql: &str, reserved_markers: &[String], context: &str) -> IntrinsicCheck {
    if reserved_markers
        .iter()
        .any(|marker| sql.contains(marker.as_str()))
    {
        return IntrinsicCheck::Rejected(format!(
            "{context} contains a reserved internal cursor marker"
        ));
    }
    if !contains_intrinsic_name(sql) {
        return IntrinsicCheck::Free;
    }
    let bytes: &[u8] = sql.as_bytes();
    let mut found: bool = false;
    let mut index: usize = 0;
    while index < bytes.len() {
        let (name, end): (&str, usize) = match step(bytes, index) {
            ScanStep::Next(next) => {
                index = next;
                continue;
            }
            ScanStep::Unclosed(construct) => {
                return IntrinsicCheck::Rejected(unclosed_message(context, construct));
            }
            ScanStep::Deferred => return IntrinsicCheck::Deferred,
            ScanStep::Intrinsic { name, end } => (name, end),
        };
        match call_scan(sql, end) {
            CallScan::Called(close) => {
                found = true;
                index = close + 1;
            }
            CallScan::NotCalled => {
                return IntrinsicCheck::Rejected(format!(
                    "{context} intrinsic {name} must be called with ()"
                ));
            }
            CallScan::Arguments => {
                return IntrinsicCheck::Rejected(format!(
                    "{context} intrinsic {name} does not accept arguments"
                ));
            }
            CallScan::UnclosedParenthesis => {
                return IntrinsicCheck::Rejected(unclosed_message(
                    &format!("{context} cursor intrinsic"),
                    Unclosed::Parenthesis,
                ));
            }
            CallScan::Deferred => return IntrinsicCheck::Deferred,
        }
    }
    if found {
        IntrinsicCheck::Rejected(format!(
            "{context} uses cursor intrinsics, which are only supported in cursor-based \
             incremental model query SQL"
        ))
    } else {
        IntrinsicCheck::Free
    }
}
