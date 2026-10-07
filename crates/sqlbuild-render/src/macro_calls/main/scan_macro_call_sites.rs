//! Top-level macro call sites of one authored SQL string, as Python's expansion loop visits them.

use sqlbuild_core::text::models::PythonText;

use crate::macro_calls::_helpers::offsets::char_offsets;
use crate::macro_calls::_helpers::scanner::{
    mentions_typed_reference, nested_names, top_level_calls,
};
use crate::macro_calls::models::{MacroCallSite, ScanDeferral};

/// Every top-level call site in order under `python`'s character classes, or a deferral.
pub fn scan_macro_call_sites(
    python: PythonText,
    sql: &str,
) -> Result<Vec<MacroCallSite>, ScanDeferral> {
    let calls = top_level_calls(python, sql)?;
    let boundaries: Vec<usize> = calls
        .iter()
        .flat_map(|call| [call.start, call.close + 1])
        .collect();
    let offsets = char_offsets(sql, &boundaries);
    calls
        .into_iter()
        .zip(offsets.as_chunks::<2>().0)
        .map(|(call, offsets)| {
            let args = &sql[call.open + 1..call.close];
            let mut tree_names: Vec<String> = vec![call.name.clone()];
            for name in nested_names(python, args)? {
                if !tree_names.contains(&name) {
                    tree_names.push(name);
                }
            }
            Ok(MacroCallSite {
                start: offsets[0],
                end: offsets[1],
                name: call.name,
                tree_names,
                typed_reference_text: mentions_typed_reference(args),
            })
        })
        .collect()
}
