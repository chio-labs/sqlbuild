use polyglot_sql::tokens::{Span, Token, TokenType};

use crate::sql_lint::_helpers::engine::is_query_from;

struct InlineRelationContext<'a> {
    tokens: &'a [Token],
    depths: &'a [usize],
    scopes: Vec<Option<usize>>,
    significant: &'a [usize],
}

pub(super) fn collect_inline_query_relation_spans(
    tokens: &[Token],
    depths: &[usize],
    significant: &[usize],
) -> Vec<Span> {
    let context = InlineRelationContext {
        tokens,
        depths,
        scopes: token_scopes(tokens),
        significant,
    };
    (0..significant.len())
        .filter_map(|position| inline_query_relation_span(&context, position))
        .collect()
}

fn inline_query_relation_span(
    context: &InlineRelationContext<'_>,
    position: usize,
) -> Option<Span> {
    let &opening = context.significant.get(position)?;
    if context.tokens[opening].token_type != TokenType::LParen {
        return None;
    }
    let marker_position = position.checked_sub(1)?;
    let previous = context.significant[marker_position];
    if context.tokens[previous].token_type == TokenType::Lateral
        || context.tokens[previous].text.eq_ignore_ascii_case("apply")
        || !is_query_relation_marker(context, marker_position)
    {
        return None;
    }

    let mut candidate_position = position + 1;
    let mut candidate_depth = context.depths[opening] + 1;
    loop {
        let &candidate = context.significant.get(candidate_position)?;
        if context.depths[candidate] != candidate_depth {
            return None;
        }
        if context.tokens[candidate].token_type == TokenType::LParen {
            candidate_position += 1;
            candidate_depth += 1;
            continue;
        }
        return is_query_start(&context.tokens[candidate])
            .then_some(context.tokens[candidate].span);
    }
}

fn is_query_relation_marker(context: &InlineRelationContext<'_>, marker_position: usize) -> bool {
    let marker = context.significant[marker_position];
    if !(is_query_from(context.tokens, marker)
        || matches!(
            context.tokens[marker].token_type,
            TokenType::Join | TokenType::Comma
        ))
    {
        return false;
    }
    let scope = context.scopes[marker];
    let Some(select_position) = (0..marker_position).rev().find(|&position| {
        let index = context.significant[position];
        context.scopes[index] == scope && context.tokens[index].token_type == TokenType::Select
    }) else {
        return false;
    };
    let query_clause = &context.significant[select_position + 1..marker_position];
    if query_clause.iter().any(|&index| {
        context.scopes[index] == scope
            && matches!(
                context.tokens[index].token_type,
                TokenType::Semicolon | TokenType::Union | TokenType::Intersect | TokenType::Except
            )
    }) {
        return false;
    }
    if is_query_from(context.tokens, marker) {
        return true;
    }
    let Some(from_position) = query_clause
        .iter()
        .position(|&index| context.scopes[index] == scope && is_query_from(context.tokens, index))
    else {
        return false;
    };
    !query_clause[from_position + 1..].iter().any(|&index| {
        context.scopes[index] == scope && is_post_relation_clause(context.tokens[index].token_type)
    })
}

fn is_query_start(token: &Token) -> bool {
    matches!(token.token_type, TokenType::Select | TokenType::Values)
        || token.text.eq_ignore_ascii_case("with")
}

fn is_post_relation_clause(token_type: TokenType) -> bool {
    matches!(
        token_type,
        TokenType::Where
            | TokenType::Group
            | TokenType::Having
            | TokenType::Qualify
            | TokenType::Order
            | TokenType::Limit
            | TokenType::Offset
            | TokenType::Fetch
    )
}

fn token_scopes(tokens: &[Token]) -> Vec<Option<usize>> {
    let mut openings: Vec<usize> = Vec::new();
    tokens
        .iter()
        .enumerate()
        .map(|(index, token)| {
            let scope = openings.last().copied();
            if matches!(
                token.token_type,
                TokenType::LParen | TokenType::LBracket | TokenType::LBrace
            ) {
                openings.push(index);
            } else if matches!(
                token.token_type,
                TokenType::RParen | TokenType::RBracket | TokenType::RBrace
            ) {
                let _ = openings.pop();
            }
            scope
        })
        .collect()
}
