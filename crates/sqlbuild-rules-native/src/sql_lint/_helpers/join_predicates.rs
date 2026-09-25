use polyglot_sql::DialectType;
use polyglot_sql::expressions::Expression;
use polyglot_sql::parser::{Parser, ParserConfig};
use polyglot_sql::tokens::{Span, Token, TokenType};

pub(super) fn join_expression_spans(
    tokens: &[Token],
    depths: &[usize],
    dialect: DialectType,
) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.token_type != TokenType::On {
            continue;
        }
        let clause = (0..index).rev().find(|&previous| {
            depths[previous] == depths[index]
                && matches!(
                    tokens[previous].token_type,
                    TokenType::Join
                        | TokenType::Select
                        | TokenType::Where
                        | TokenType::From
                        | TokenType::On
                )
        });
        if clause.is_none_or(|previous| tokens[previous].token_type != TokenType::Join) {
            continue;
        }
        let end = (index + 1..tokens.len())
            .find(|&next| {
                depths[next] < depths[index]
                    || (depths[next] == depths[index]
                        && matches!(
                            tokens[next].token_type,
                            TokenType::Join
                                | TokenType::Where
                                | TokenType::Group
                                | TokenType::Having
                                | TokenType::Qualify
                                | TokenType::Order
                                | TokenType::Limit
                                | TokenType::Union
                                | TokenType::Intersect
                                | TokenType::Except
                                | TokenType::Semicolon
                        ))
            })
            .unwrap_or(tokens.len());
        let mut parser = Parser::with_config(
            tokens[index + 1..end].to_vec(),
            ParserConfig {
                dialect: Some(dialect),
                ..Default::default()
            },
        );
        if !matches!(parser.parse_expressions(), Ok(Some(ref predicate)) if plain_predicate(predicate))
        {
            spans.push(token.span);
        }
    }
    spans
}

fn plain_column(expression: &Expression) -> bool {
    matches!(
        expression,
        Expression::Column(_) | Expression::Identifier(_)
    ) || matches!(expression, Expression::Paren(value) if plain_column(&value.this))
}

fn literal(expression: &Expression) -> bool {
    matches!(
        expression,
        Expression::Literal(_) | Expression::Boolean(_) | Expression::Null(_)
    ) || matches!(expression, Expression::Neg(value) if matches!(&value.this, Expression::Literal(_)))
}

fn operand(expression: &Expression) -> bool {
    plain_column(expression) || literal(expression)
}

fn comparison(left: &Expression, right: &Expression) -> bool {
    operand(left) && operand(right) && (plain_column(left) || plain_column(right))
}

fn plain_predicate(expression: &Expression) -> bool {
    match expression {
        Expression::Paren(value) => plain_predicate(&value.this),
        Expression::And(value) | Expression::Or(value) => {
            plain_predicate(&value.left) && plain_predicate(&value.right)
        }
        Expression::Eq(value)
        | Expression::Neq(value)
        | Expression::Lt(value)
        | Expression::Lte(value)
        | Expression::Gt(value)
        | Expression::Gte(value)
        | Expression::NullSafeEq(value)
        | Expression::NullSafeNeq(value)
        | Expression::Adjacent(value)
        | Expression::ArrayContainsAll(value)
        | Expression::ArrayContainedBy(value)
        | Expression::ArrayOverlaps(value)
        | Expression::ExtendsLeft(value)
        | Expression::ExtendsRight(value)
        | Expression::Match(value)
        | Expression::TsMatch(value) => comparison(&value.left, &value.right),
        Expression::Like(value) | Expression::ILike(value) => {
            comparison(&value.left, &value.right)
                && value.escape.as_ref().is_none_or(literal)
                && value.quantifier.is_none()
        }
        Expression::Between(value) => {
            plain_column(&value.this) && operand(&value.low) && operand(&value.high)
        }
        Expression::In(value) => {
            plain_column(&value.this)
                && value.query.is_none()
                && value.unnest.is_none()
                && !value.is_field
                && !value.expressions.is_empty()
                && value.expressions.iter().all(literal)
        }
        Expression::IsNull(value) => plain_column(&value.this),
        _ => false,
    }
}
