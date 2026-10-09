//! Parse one macro call's argument text as Python's literal grammar, with native errors.

use crate::macro_arguments::_helpers::evaluation::evaluate_arguments;
use crate::macro_arguments::_helpers::failures::Failure;
use crate::macro_arguments::_helpers::lexer::tokenize;
use crate::macro_arguments::_helpers::syntax_tree::parse_call_arguments;
use crate::macro_arguments::models::{ArgumentError, MacroArguments};
use crate::macro_arguments::types::ArgumentHost;

/// The value plan of `text`, whose nested macro calls fill the `[start, end)` code point spans.
pub fn parse_macro_arguments(
    host: &dyn ArgumentHost,
    text: &str,
    nested: &[(usize, usize)],
) -> Result<MacroArguments, ArgumentError> {
    let characters: Vec<char> = text.chars().collect();
    tokenize(host, &characters, nested)
        .and_then(|tokens| parse_call_arguments(&tokens))
        .and_then(|arguments| evaluate_arguments(&arguments))
        .map_err(|failure| located(&characters, failure))
}

fn located(characters: &[char], failure: Failure) -> ArgumentError {
    let mut line: usize = 1;
    let mut line_start: usize = 0;
    let mut index: usize = 0;
    while index < failure.position.min(characters.len()) {
        let character: char = characters[index];
        index += 1;
        if character == '\n' || (character == '\r' && characters.get(index) != Some(&'\n')) {
            line += 1;
            line_start = index;
        }
    }
    ArgumentError {
        detail: failure.detail,
        help: failure.help.to_owned(),
        line,
        column: failure.position - line_start + 1,
    }
}
