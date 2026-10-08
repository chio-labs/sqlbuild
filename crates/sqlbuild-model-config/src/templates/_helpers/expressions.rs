//! The Python template expression parser.

use crate::templates::_helpers::tokens::{Token, TokenKind, tokenize};
use crate::templates::errors::TemplateError;
use crate::templates::models::{Expression, TemplateFailure};

/// Parse one `${...}` body into an expression.
pub(crate) fn parse_expression(body: &str) -> Result<Expression, TemplateFailure> {
    let tokens: Vec<Token> = tokenize(body)?;
    let mut parser = Parser { tokens, index: 0 };
    let expression = parser.expression()?;
    let token: &Token = parser.peek();
    if token.kind == TokenKind::End {
        Ok(expression)
    } else {
        Err(unexpected(token))
    }
}

struct Parser {
    tokens: Vec<Token>,
    index: usize,
}

fn unexpected(token: &Token) -> TemplateFailure {
    TemplateFailure::Invalid(TemplateError::UnexpectedToken(
        token.value(),
        token.position,
    ))
}

impl Parser {
    fn peek(&self) -> &Token {
        &self.tokens[self.index]
    }

    fn match_symbol(&mut self, symbol: char) -> bool {
        if self.peek().kind == TokenKind::Symbol(symbol) {
            self.index += 1;
            true
        } else {
            false
        }
    }

    fn expression(&mut self) -> Result<Expression, TemplateFailure> {
        let token: Token = self.peek().clone();
        match token.kind {
            TokenKind::Text(text) => {
                self.index += 1;
                Ok(Expression::Text(text))
            }
            TokenKind::Word(word) => {
                self.index += 1;
                if self.match_symbol('(') {
                    self.function_call(word)
                } else {
                    Ok(Expression::Reference(word))
                }
            }
            TokenKind::Symbol(_) | TokenKind::End => Err(unexpected(&token)),
        }
    }

    fn function_call(&mut self, name: String) -> Result<Expression, TemplateFailure> {
        let mut arguments: Vec<Expression> = Vec::new();
        while self.peek().kind != TokenKind::Symbol(')') {
            arguments.push(self.expression()?);
            if !self.match_symbol(',') {
                break;
            }
        }
        if self.match_symbol(')') {
            Ok(Expression::Function { name, arguments })
        } else {
            Err(TemplateFailure::Invalid(TemplateError::ExpectedSymbol(
                ')',
                self.peek().position,
            )))
        }
    }
}
