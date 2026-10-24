//! The form of a SQL macro body, as its definition reads it.

use crate::sql_macros::_helpers::parsing::definition::body_form;
use crate::sql_macros::_helpers::parsing::lexing::tokens;
use crate::sql_macros::models::SqlMacroForm;

/// Whether `body` is a CTE list, a column list or an expression, from its first token.
#[must_use]
pub fn sql_macro_body_form(body: &str) -> SqlMacroForm {
    match tokens(body) {
        Ok(scanned) => body_form(body, &scanned),
        Err(_) => SqlMacroForm::Expression,
    }
}
