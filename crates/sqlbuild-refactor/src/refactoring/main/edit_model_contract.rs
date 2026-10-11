//! Contract adoption's metadata-preserving MODEL header edit.

use sqlbuild_sqltext::compiler::main::model_header_columns::model_header_columns;

use crate::refactoring::_helpers::contracts::model_edits::{
    columns_block, columns_edit, fixed_physical_columns, ownership_conflict,
};
use crate::refactoring::_helpers::edits::header_edits::model_header_body_span;
use crate::refactoring::_helpers::scanning::chars::{chars, slice};
use crate::refactoring::constants::MODEL_HEADER_CONFLICT;
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{ContractEdit, ContractModelRequest};

/// Python's `edit_model`: add, retype or drop MODEL header columns to match the physical ones.
pub fn edit_model_contract(request: &ContractModelRequest) -> Result<ContractEdit, RefactorError> {
    if let Some(conflict) = ownership_conflict(request) {
        return Ok(conflict);
    }
    let physical = fixed_physical_columns(request)?;
    let text = chars(&request.contents);
    let body = model_header_body_span(&request.contents);
    match model_header_columns(&request.contents).map_err(RefactorError::value)? {
        Some(columns) => columns_edit(&text, request, &columns, &physical),
        None => Ok(body.map_or_else(
            || ContractEdit::Conflict(MODEL_HEADER_CONFLICT.to_owned()),
            |(_, insertion)| {
                ContractEdit::Edited(format!(
                    "{}{}{}",
                    slice(&text, 0, insertion),
                    columns_block(&physical),
                    slice(&text, insertion, text.len())
                ))
            },
        )),
    }
}
