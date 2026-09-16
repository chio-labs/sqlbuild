use sqlparser::dialect::Dialect;
use sqlparser::tokenizer::{Token, Tokenizer};
use std::collections::BTreeSet;

pub(super) fn numeric_literal_tokens(
    source: &str,
    dialect: &dyn Dialect,
) -> Result<BTreeSet<String>, String> {
    let tokens = Tokenizer::new(dialect, source)
        .tokenize()
        .map_err(|error| format!("could not tokenize authored numeric literals: {error}"))?;
    let tokens = tokens
        .iter()
        .filter(|token| !matches!(token, Token::Whitespace(_)))
        .collect::<Vec<_>>();
    let has_model_header = matches!(
        tokens.first(),
        Some(Token::Word(word))
            if word.quote_style.is_none() && word.value.eq_ignore_ascii_case("model")
    ) && matches!(tokens.get(1), Some(Token::LParen));
    let model_header_end = has_model_header
        .then(|| {
            tokens
                .iter()
                .position(|token| matches!(token, Token::SemiColon))
        })
        .flatten();
    let query_start = if has_model_header {
        model_header_end.map_or(0, |end| end + 1)
    } else {
        0
    };
    let mut literals: BTreeSet<String> = BTreeSet::new();
    for (index, token) in tokens[query_start..].iter().enumerate() {
        let Token::Number(number, _) = token else {
            continue;
        };
        literals.insert(number.to_string());
        if index > 0 && matches!(tokens[query_start + index - 1], Token::Minus) {
            literals.insert(format!("-{number}"));
        }
    }
    Ok(literals)
}
