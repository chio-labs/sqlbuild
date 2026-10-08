//! Python's `expand_test_parameters` scan, leaving value rendering to the caller.

use crate::sql_lexing::main::python_non_code_end::python_non_code_end;
use crate::sql_lexing::main::unclosed_construct::unclosed_construct;
use crate::sql_lexing::main::unclosed_message::unclosed_message;
use crate::sql_lexing::models::NonCode;
use crate::test_parameters::_helpers::reference::{parameter_token_at, reference_at};
use crate::test_parameters::models::{ParameterReference, ParameterScan};

/// Every active reference in order up to Python's first error for `owner`, the SQL test case.
#[must_use]
pub fn parameter_references(sql: &str, declared: &[String], owner: &str) -> ParameterScan {
    let bytes: &[u8] = sql.as_bytes();
    let mut references: Vec<ParameterReference> = Vec::new();
    let mut index: usize = 0;
    let mut characters: usize = 0;
    let stop = |references: Vec<ParameterReference>, error: String| ParameterScan {
        references,
        error: Some(error),
    };
    while index < bytes.len() {
        match python_non_code_end(bytes, index) {
            NonCode::End(end) => {
                characters += sql[index..end].chars().count();
                index = end;
                continue;
            }
            NonCode::Raises => {
                let construct = unclosed_construct(bytes, index);
                return stop(references, unclosed_message("SQL", construct));
            }
            NonCode::Code => {}
        }
        if parameter_token_at(bytes, index) {
            let Some((name, end)) = reference_at(sql, index) else {
                return stop(
                    references,
                    format!("{owner} has malformed @param reference; expected @param(\"name\")"),
                );
            };
            if !declared.iter().any(|candidate| candidate == name) {
                return stop(
                    references,
                    format!("{owner} references undeclared parameter '{name}'"),
                );
            }
            let length: usize = sql[index..end].chars().count();
            references.push(ParameterReference {
                start: characters,
                end: characters + length,
                name: name.to_owned(),
            });
            characters += length;
            index = end;
            continue;
        }
        let width: usize = sql[index..].chars().next().map_or(1, char::len_utf8);
        characters += 1;
        index += width;
    }
    ParameterScan {
        references,
        error: None,
    }
}
