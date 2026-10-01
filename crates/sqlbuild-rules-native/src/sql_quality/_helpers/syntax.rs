//! Shared syntax helpers for SQL quality Rules.

use std::collections::HashMap;

use polyglot_sql::expressions::{Column, Select, Star};
use polyglot_sql::tokens::{Token, TokenType};
use polyglot_sql::{Expression, ExpressionWalk};

use crate::sql_quality::constants::MIN_REMOVABLE_OUTPUTS;

/// One projection of a select list.
pub(super) enum Projection<'a> {
    Named {
        name: String,
        expression: &'a Expression,
    },
    Star(&'a Star),
    Unnamed,
}

pub(super) fn lower(name: &str) -> String {
    name.to_ascii_lowercase()
}

pub(super) fn projections(select: &Select) -> Vec<Projection<'_>> {
    select
        .expressions
        .iter()
        .map(|expression| match expression {
            Expression::Alias(alias) => Projection::Named {
                name: lower(&alias.alias.name),
                expression: &alias.this,
            },
            Expression::Column(column) => Projection::Named {
                name: lower(&column.name.name),
                expression,
            },
            Expression::Star(star) => Projection::Star(star),
            _ => Projection::Unnamed,
        })
        .collect()
}

pub(super) fn columns(expression: &Expression) -> Vec<&Column> {
    expression
        .dfs()
        .filter_map(|node| match node {
            Expression::Column(column) => Some(column.as_ref()),
            _ => None,
        })
        .collect()
}

pub(super) fn qualifier(column: &Column) -> Option<String> {
    column.table.as_ref().map(|table| lower(&table.name))
}

/// Relations read directly by one select: `(alias, relation name, expression)`.
pub(super) fn sources(select: &Select) -> Vec<(String, Option<String>, &Expression)> {
    let mut found: Vec<(String, Option<String>, &Expression)> = Vec::new();
    let from = select.from.iter().flat_map(|from| from.expressions.iter());
    for expression in from.chain(select.joins.iter().map(|join| &join.this)) {
        match expression {
            Expression::Table(table) => {
                let name: String = lower(&table.name.name);
                let alias: String = table
                    .alias
                    .as_ref()
                    .map_or_else(|| name.clone(), |alias| lower(&alias.name));
                found.push((alias, Some(name), expression));
            }
            Expression::Subquery(subquery) => {
                let alias: String = subquery
                    .alias
                    .as_ref()
                    .map_or_else(String::new, |alias| lower(&alias.name));
                found.push((alias, None, expression));
            }
            _ => found.push((String::new(), None, expression)),
        }
    }
    found
}

/// Token index of the SELECT opening each `name AS (SELECT` CTE body, by lower-cased name.
pub(super) fn cte_select_tokens(tokens: &[Token]) -> HashMap<String, usize> {
    let significant: Vec<usize> = (0..tokens.len())
        .filter(|&index| !is_trivia(&tokens[index]))
        .collect();
    let mut found: HashMap<String, usize> = HashMap::new();
    for window in significant.windows(4) {
        let [name_index, as_index, paren_index, select_index] = window else {
            continue;
        };
        if tokens[*as_index].token_type == TokenType::As
            && tokens[*paren_index].token_type == TokenType::LParen
            && tokens[*select_index].token_type == TokenType::Select
        {
            found
                .entry(lower(&tokens[*name_index].text))
                .or_insert(*select_index);
        }
    }
    found
}

/// The comma-inclusive deletion span that removes projection `index` from `spans`.
pub(super) fn projection_removal(spans: &[(usize, usize)], index: usize) -> Option<(usize, usize)> {
    if spans.len() < MIN_REMOVABLE_OUTPUTS {
        return None;
    }
    let (start, end) = spans[index];
    if index + 1 < spans.len() {
        Some((start, spans[index + 1].0))
    } else {
        Some((spans[index - 1].1, end))
    }
}

pub(super) fn is_trivia(token: &Token) -> bool {
    matches!(
        token.token_type,
        TokenType::Space | TokenType::Break | TokenType::LineComment | TokenType::BlockComment
    )
}
