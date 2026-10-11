//! Contract adoption's line-based YAML source declaration edit.

use crate::refactoring::_helpers::contracts::source_edits::{
    column_edits, columns_insertion, columns_key, is_generated,
};
use crate::refactoring::_helpers::contracts::yaml_lines::{lines_with_breaks, named_block};
use crate::refactoring::constants::{GENERATED_SOURCE_CONFLICT, SOURCE_BLOCK_CONFLICT};
use crate::refactoring::models::{ContractEdit, ContractSourceRequest};

/// Python's `edit_source`: add, retype or drop a source's YAML columns to match the physical ones.
pub fn edit_source_contract(request: &ContractSourceRequest) -> ContractEdit {
    if is_generated(&request.discovered_contents) {
        return ContractEdit::Conflict(GENERATED_SOURCE_CONFLICT.to_owned());
    }
    let mut lines = lines_with_breaks(&request.contents);
    let views: Vec<&str> = lines.iter().map(String::as_str).collect();
    let Some(block) = named_block(&views, &request.name) else {
        return ContractEdit::Conflict(SOURCE_BLOCK_CONFLICT.to_owned());
    };
    let mut line_edits = match columns_key(&views, block) {
        None => vec![(block.1, block.1, columns_insertion(request, block.2))],
        Some(columns_index) => match column_edits(request, &views, (columns_index, block.1)) {
            Ok(line_edits) => line_edits,
            Err(conflict) => return ContractEdit::Conflict(conflict),
        },
    };
    line_edits.sort_by(|left, right| right.cmp(left));
    for (start, end, replacement) in line_edits {
        lines.splice(start..end, replacement);
    }
    ContractEdit::Edited(lines.concat())
}
