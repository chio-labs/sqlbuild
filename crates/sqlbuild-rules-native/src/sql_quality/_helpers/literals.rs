//! SQBRSQL044: string literals longer than the project limit.

use std::borrow::Cow;

use polyglot_sql::tokens::TokenType;

use crate::configuration::main::setting_help::setting_help;
use crate::sql_lint::models::LintDiagnostic;
use crate::sql_quality::constants::{
    LONG_LITERAL, LONG_LITERAL_GUIDANCE, MAX_LITERAL_LENGTH_KEY, RULES_THRESHOLDS_SECTION,
};
use crate::sql_quality::models::QualityRequest;

const CONSTANT_FIX_REFUSAL: &str =
    "Moving the value to a constant requires choosing its name and placement";

pub(crate) fn diagnostics(request: &QualityRequest<'_>) -> Vec<LintDiagnostic> {
    request
        .tokens
        .iter()
        .filter(|token| is_string(token.token_type))
        .filter_map(|token| {
            let length: usize = token.text.chars().count();
            (length > request.max_literal_length).then(|| LintDiagnostic {
                code: LONG_LITERAL.code,
                message: LONG_LITERAL.message,
                remediation: Cow::Owned(remediation(length, request.max_literal_length)),
                start: token.span.start,
                end: token.span.end,
                fix: None,
                fix_unavailable_reason: Some(CONSTANT_FIX_REFUSAL),
            })
        })
        .collect()
}

fn remediation(length: usize, limit: usize) -> String {
    format!(
        "{LONG_LITERAL_GUIDANCE} {}",
        setting_help(
            &format!("To allow literals of {length} characters (the current value is {limit})"),
            RULES_THRESHOLDS_SECTION,
            MAX_LITERAL_LENGTH_KEY,
            &length.to_string(),
        )
    )
}

fn is_string(kind: TokenType) -> bool {
    matches!(
        kind,
        TokenType::String
            | TokenType::DollarString
            | TokenType::EscapeString
            | TokenType::RawString
            | TokenType::NationalString
            | TokenType::UnicodeString
            | TokenType::ByteString
            | TokenType::TripleSingleQuotedString
            | TokenType::TripleDoubleQuotedString
            | TokenType::HeredocString
            | TokenType::HeredocStringAlternative
    )
}
