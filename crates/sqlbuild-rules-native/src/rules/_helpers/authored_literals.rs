use sqlparser::dialect::Dialect;
use sqlparser::tokenizer::{Token, Tokenizer};
use std::collections::BTreeSet;

#[derive(Clone, Copy)]
struct CastScope {
    depth: usize,
    in_type: bool,
}

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
    let mut cast_scopes: Vec<CastScope> = Vec::new();
    let mut depth = 0_usize;
    for (index, token) in tokens[query_start..].iter().enumerate() {
        match token {
            Token::LParen => {
                depth += 1;
                if index > 0
                    && matches!(
                        tokens[query_start + index - 1],
                        Token::Word(word)
                            if word.quote_style.is_none()
                                && matches!(
                                    word.value.to_ascii_uppercase().as_str(),
                                    "CAST" | "TRY_CAST"
                                )
                    )
                {
                    cast_scopes.push(CastScope {
                        depth,
                        in_type: false,
                    });
                }
            }
            Token::RParen => {
                if cast_scopes.last().is_some_and(|scope| scope.depth == depth) {
                    cast_scopes.pop();
                }
                depth = depth.saturating_sub(1);
            }
            Token::Word(word)
                if word.quote_style.is_none()
                    && word.value.eq_ignore_ascii_case("as")
                    && cast_scopes.last().is_some_and(|scope| scope.depth == depth) =>
            {
                if let Some(scope) = cast_scopes.last_mut() {
                    scope.in_type = true;
                }
            }
            Token::Number(number, _) if !cast_scopes.last().is_some_and(|scope| scope.in_type) => {
                literals.insert(number.to_string());
                if index > 0 && matches!(tokens[query_start + index - 1], Token::Minus) {
                    literals.insert(format!("-{number}"));
                }
            }
            _ => {}
        }
    }
    Ok(literals)
}
