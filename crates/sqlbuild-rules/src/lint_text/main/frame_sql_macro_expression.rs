//! `frame_sql_macro_expression`: an expression macro body as the one column of a `SELECT`.

use crate::lint_text::constants::{EXPRESSION_SELECT_PREFIX, LINTED_EXPRESSION_ALIAS};
use crate::lint_text::models::{ExpansionSpan, FramedExpression};

/// `SELECT <expression> AS <alias>`, the statement the native parser reads an expression body as.
pub fn frame_sql_macro_expression(expanded: &str) -> FramedExpression {
    let mut core_end: usize = expanded.trim_end().len();
    if expanded[..core_end].ends_with(';') {
        core_end = expanded[..core_end - 1].trim_end().len();
    }
    let suffix: String = format!("\nAS {LINTED_EXPRESSION_ALIAS}");
    let text: String = format!(
        "{EXPRESSION_SELECT_PREFIX}{}{suffix}{}",
        &expanded[..core_end],
        &expanded[core_end..]
    );
    let prefix_chars: usize = EXPRESSION_SELECT_PREFIX.chars().count();
    let core_chars: usize = expanded[..core_end].chars().count();
    let suffix_chars: usize = suffix.chars().count();
    let offset = |value: usize| i64::try_from(value).unwrap_or(i64::MAX);
    let span = |at: usize, output_start: usize, length: usize| ExpansionSpan {
        source_start: offset(at),
        source_end: offset(at),
        output_start: offset(output_start),
        output_end: offset(output_start + length),
    };
    FramedExpression {
        text,
        pass: vec![
            span(0, 0, prefix_chars),
            span(core_chars, prefix_chars + core_chars, suffix_chars),
        ],
        frame: (
            offset(prefix_chars),
            offset(suffix_chars + expanded[core_end..].chars().count()),
        ),
    }
}
