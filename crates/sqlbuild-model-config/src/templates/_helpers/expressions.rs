//! The Python template expression parser.

use crate::templates::_helpers::tokens::{Token, tokenize};
use crate::templates::models::{Expression, TemplateFailure};

/// Parse one `${...}` body into an expression.
pub(crate) fn parse_expression(body: &str) -> Result<Expression, TemplateFailure> {
    let tokens: Vec<Token> = tokenize(body)?;
    let mut parser = Parser { tokens, index: 0 };
    let expression = parser.expression()?;
    if parser.peek() == &Token::End {
        Ok(expression)
    } else {
        Err(TemplateFailure::Invalid)
    }
}

struct Parser {
    tokens: Vec<Token>,
    index: usize,
}

impl Parser {
    fn peek(&self) -> &Token {
        &self.tokens[self.index]
    }

    fn advance(&mut self) -> Token {
        let token = self.tokens[self.index].clone();
        self.index += 1;
        token
    }

    fn match_symbol(&mut self, symbol: char) -> bool {
        if self.peek() == &Token::Symbol(symbol) {
            self.index += 1;
            true
        } else {
            false
        }
    }

    fn expression(&mut self) -> Result<Expression, TemplateFailure> {
        match self.peek() {
            Token::Text(_) => match self.advance() {
                Token::Text(text) => Ok(Expression::Text(text)),
                _ => Err(TemplateFailure::Invalid),
            },
            Token::Word(_) => {
                let Token::Word(word) = self.advance() else {
                    return Err(TemplateFailure::Invalid);
                };
                if self.match_symbol('(') {
                    self.function_call(word)
                } else {
                    Ok(Expression::Reference(word))
                }
            }
            Token::Symbol(_) | Token::End => Err(TemplateFailure::Invalid),
        }
    }

    fn function_call(&mut self, name: String) -> Result<Expression, TemplateFailure> {
        let mut arguments: Vec<Expression> = Vec::new();
        while self.peek() != &Token::Symbol(')') {
            arguments.push(self.expression()?);
            if !self.match_symbol(',') {
                break;
            }
        }
        if self.match_symbol(')') {
            Ok(Expression::Function { name, arguments })
        } else {
            Err(TemplateFailure::Invalid)
        }
    }
}
