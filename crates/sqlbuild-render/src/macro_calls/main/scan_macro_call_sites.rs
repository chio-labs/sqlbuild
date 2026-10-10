//! Top-level macro call sites of one authored SQL string, as Python's expansion loop visits them.

use sqlbuild_core::text::models::PythonText;

use crate::macro_calls::_helpers::offsets::char_offsets;
use crate::macro_calls::_helpers::scanner::{
    ScannedFailure, mentions_typed_reference, nested_names, top_level_calls,
};
use crate::macro_calls::models::{MacroCallScan, MacroCallSite, MacroScanFailure};

/// Every complete top-level call site in order under `python`'s character classes, and where
/// Python's scan raises, if it does.
pub fn scan_macro_call_sites(python: PythonText, sql: &str) -> MacroCallScan {
    let (calls, failure) = top_level_calls(python, sql);
    let mut boundaries: Vec<usize> = calls
        .iter()
        .flat_map(|call| [call.start, call.close + 1])
        .collect();
    let failed_call: Option<usize> = failure.as_ref().and_then(|failure| failure.call_start);
    boundaries.extend(failed_call);
    let offsets = char_offsets(sql, &boundaries);
    let sites: Vec<MacroCallSite> = calls
        .into_iter()
        .zip(offsets.as_chunks::<2>().0)
        .map(|(call, offsets)| {
            let args = &sql[call.open + 1..call.close];
            let tree_names: Option<Vec<String>> = nested_names(python, args).ok().map(|nested| {
                let mut tree_names: Vec<String> = vec![call.name.clone()];
                for name in nested {
                    if !tree_names.contains(&name) {
                        tree_names.push(name);
                    }
                }
                tree_names
            });
            MacroCallSite {
                start: offsets[0],
                end: offsets[1],
                name: call.name,
                tree_names,
                typed_reference_text: mentions_typed_reference(args),
            }
        })
        .collect();
    MacroCallScan {
        sites,
        failure: failure.map(|ScannedFailure { call_start, error }| MacroScanFailure {
            call_start: call_start.and(offsets.last().copied()),
            error,
        }),
    }
}
