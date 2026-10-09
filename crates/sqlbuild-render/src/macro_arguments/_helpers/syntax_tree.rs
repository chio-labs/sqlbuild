//! Parse argument tokens into Python's `ast` node shapes for the literal subset.

use crate::macro_arguments::_helpers::failures::{
    Failure, keyword_order, missing_comma, syntax, unsupported,
};
use crate::macro_arguments::_helpers::lexer::{NumberToken, Token, TokenKind};

const PYTHON_KEYWORDS: [&str; 35] = [
    "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import",
    "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while",
    "with", "yield",
];

/// One expression node and the code point position it starts at.
#[derive(Clone, Debug)]
pub(crate) struct Node {
    pub(crate) expr: Expr,
    pub(crate) position: usize,
}

#[derive(Clone, Debug)]
pub(crate) enum Expr {
    Str {
        value: String,
        bytes: bool,
        formatted: bool,
    },
    Number(NumberToken),
    Ellipsis,
    Name(String),
    Nested(usize),
    Call {
        function: Box<Node>,
        args: Vec<Node>,
        keywords: Vec<Keyword>,
    },
    List(Vec<Node>),
    Tuple(Vec<Node>),
    Dict(Vec<(Option<Node>, Node)>),
    Set(Vec<Node>),
    Starred(Box<Node>),
    Unary {
        negative: bool,
        operand: Box<Node>,
    },
}

/// One keyword argument; `name` is `None` for `**` expansion.
#[derive(Clone, Debug)]
pub(crate) struct Keyword {
    pub(crate) name: Option<String>,
    pub(crate) value: Node,
}

/// The arguments of one call, as `ast.Call.args` and `ast.Call.keywords`.
pub(crate) struct CallArguments {
    pub(crate) args: Vec<Node>,
    pub(crate) keywords: Vec<Keyword>,
}

struct Parser<'tokens> {
    tokens: &'tokens [Token],
    index: usize,
}

/// Parse every token as the arguments of one call.
pub(crate) fn parse_call_arguments(tokens: &[Token]) -> Result<CallArguments, Failure> {
    let mut parser = Parser { tokens, index: 0 };
    let arguments: CallArguments = parser.arguments()?;
    let end: &Token = parser.peek();
    if matches!(end.kind, TokenKind::End) {
        Ok(arguments)
    } else {
        Err(parser.unexpected())
    }
}

impl Parser<'_> {
    fn peek(&self) -> &Token {
        &self.tokens[self.index]
    }

    fn peek_at(&self, offset: usize) -> Option<&Token> {
        self.tokens.get(self.index + offset)
    }

    fn at_operator(&self, operator: &str) -> bool {
        matches!(self.peek().kind, TokenKind::Operator(found) if found == operator)
    }

    fn eat(&mut self, operator: &str) -> bool {
        let found: bool = self.at_operator(operator);
        if found {
            self.index += 1;
        }
        found
    }

    /// The error for the next token where no supported argument can continue.
    fn unexpected(&self) -> Failure {
        let token: &Token = self.peek();
        if self.missing_comma() {
            return missing_comma(token.position);
        }
        match &token.kind {
            TokenKind::End => syntax(
                "the arguments end where a value is expected",
                token.position,
            ),
            TokenKind::Operator(")" | "]" | "}") => syntax(
                "a closing bracket does not match an opening one",
                token.position,
            ),
            _ => unsupported(token.position),
        }
    }

    /// Whether the next token starts a value right after one ended, so a comma is missing.
    fn missing_comma(&self) -> bool {
        let starts_value: bool = matches!(
            self.peek().kind,
            TokenKind::Str(_)
                | TokenKind::Number(_)
                | TokenKind::Name(_)
                | TokenKind::Nested(_)
                | TokenKind::Operator("{")
        );
        let ends_value: bool = self
            .index
            .checked_sub(1)
            .and_then(|previous| self.tokens.get(previous))
            .is_some_and(|token| {
                matches!(
                    token.kind,
                    TokenKind::Str(_)
                        | TokenKind::Number(_)
                        | TokenKind::Name(_)
                        | TokenKind::Nested(_)
                        | TokenKind::Operator(")" | "]" | "}")
                )
            });
        starts_value && ends_value
    }

    /// Arguments up to a `)` or the end, as Python's call grammar orders them.
    fn arguments(&mut self) -> Result<CallArguments, Failure> {
        let mut args: Vec<Node> = Vec::new();
        let mut keywords: Vec<Keyword> = Vec::new();
        let mut expanded: bool = false;
        while !matches!(self.peek().kind, TokenKind::End) && !self.at_operator(")") {
            let position: usize = self.peek().position;
            if self.eat("**") {
                expanded = true;
                keywords.push(Keyword {
                    name: None,
                    value: self.expression()?,
                });
            } else if let Some(name) = self.keyword_name()? {
                if keywords
                    .iter()
                    .any(|keyword| keyword.name.as_deref() == Some(&name))
                {
                    return Err(keyword_order(
                        &format!("could not be parsed: keyword argument '{name}' is repeated"),
                        position,
                    ));
                }
                keywords.push(Keyword {
                    name: Some(name),
                    value: self.expression()?,
                });
            } else {
                if !keywords.is_empty() {
                    let detail: &str = if expanded {
                        "could not be parsed: a positional argument follows ** expansion"
                    } else {
                        "could not be parsed: a positional argument follows a keyword argument"
                    };
                    return Err(keyword_order(detail, position));
                }
                args.push(self.starred_or_expression()?);
            }
            if !self.eat(",") {
                break;
            }
        }
        Ok(CallArguments { args, keywords })
    }

    /// `name=` starting a keyword argument, consumed, or `None` without consuming.
    fn keyword_name(&mut self) -> Result<Option<String>, Failure> {
        let TokenKind::Name(name) = &self.peek().kind else {
            return Ok(None);
        };
        let assigns: bool = matches!(
            self.peek_at(1).map(|token| &token.kind),
            Some(TokenKind::Operator("="))
        ) && !matches!(
            self.peek_at(2).map(|token| &token.kind),
            Some(TokenKind::Operator("="))
        );
        if !assigns {
            return Ok(None);
        }
        let name: String = name.clone();
        let position: usize = self.peek().position;
        if PYTHON_KEYWORDS.contains(&name.as_str()) {
            return Err(syntax(
                &format!("'{name}' is a Python keyword, not an argument name"),
                position,
            ));
        }
        self.index += 2;
        Ok(Some(name))
    }

    fn starred_or_expression(&mut self) -> Result<Node, Failure> {
        let position: usize = self.peek().position;
        if self.eat("*") {
            return Ok(Node {
                expr: Expr::Starred(Box::new(self.expression()?)),
                position,
            });
        }
        self.expression()
    }

    fn expression(&mut self) -> Result<Node, Failure> {
        let position: usize = self.peek().position;
        if self.at_operator("-") || self.at_operator("+") {
            let negative: bool = self.at_operator("-");
            self.index += 1;
            return Ok(Node {
                expr: Expr::Unary {
                    negative,
                    operand: Box::new(self.expression()?),
                },
                position,
            });
        }
        let mut node: Node = self.atom()?;
        while self.at_operator("(") {
            self.index += 1;
            let arguments: CallArguments = self.arguments()?;
            self.close(")", position)?;
            node = Node {
                expr: Expr::Call {
                    function: Box::new(node),
                    args: arguments.args,
                    keywords: arguments.keywords,
                },
                position,
            };
        }
        Ok(node)
    }

    fn close(&mut self, operator: &str, open: usize) -> Result<(), Failure> {
        if self.eat(operator) {
            return Ok(());
        }
        if matches!(self.peek().kind, TokenKind::End) {
            return Err(syntax(
                &format!("a bracket is not closed with '{operator}'"),
                open,
            ));
        }
        Err(self.unexpected())
    }

    fn atom(&mut self) -> Result<Node, Failure> {
        let token: Token = self.peek().clone();
        let expr: Expr = match token.kind {
            TokenKind::Str(_) => return Ok(self.strings()),
            TokenKind::Number(number) => Expr::Number(number),
            TokenKind::Name(name) => Expr::Name(name),
            TokenKind::Nested(call) => Expr::Nested(call),
            TokenKind::Operator("...") => Expr::Ellipsis,
            TokenKind::Operator("(") => return self.parenthesized(token.position),
            TokenKind::Operator("[") => {
                self.index += 1;
                let items: Vec<Node> = self.items("]", token.position)?;
                Expr::List(items)
            }
            TokenKind::Operator("{") => return self.braced(token.position),
            TokenKind::Operator(_) => {
                return Err(syntax("a value is missing here", token.position));
            }
            _ => return Err(self.unexpected()),
        };
        if !matches!(expr, Expr::List(_)) {
            self.index += 1;
        }
        Ok(Node {
            expr,
            position: token.position,
        })
    }

    /// Adjacent string pieces concatenate into one constant, as Python's parser joins them.
    fn strings(&mut self) -> Node {
        let position: usize = self.peek().position;
        let mut value: String = String::new();
        let mut bytes: bool = false;
        let mut formatted: bool = false;
        while let TokenKind::Str(piece) = &self.peek().kind {
            value.push_str(&piece.value);
            bytes |= piece.bytes;
            formatted |= piece.formatted;
            self.index += 1;
        }
        Node {
            expr: Expr::Str {
                value,
                bytes,
                formatted,
            },
            position,
        }
    }

    fn parenthesized(&mut self, position: usize) -> Result<Node, Failure> {
        self.index += 1;
        if self.eat(")") {
            return Ok(Node {
                expr: Expr::Tuple(Vec::new()),
                position,
            });
        }
        let first: Node = self.starred_or_expression()?;
        if !self.eat(",") {
            self.close(")", position)?;
            return Ok(first);
        }
        let mut items: Vec<Node> = vec![first];
        items.extend(self.items(")", position)?);
        Ok(Node {
            expr: Expr::Tuple(items),
            position,
        })
    }

    /// Comma-separated items up to `close`, which is consumed; a trailing comma is allowed.
    fn items(&mut self, close: &str, open: usize) -> Result<Vec<Node>, Failure> {
        let mut items: Vec<Node> = Vec::new();
        while !self.at_operator(close) && !matches!(self.peek().kind, TokenKind::End) {
            items.push(self.starred_or_expression()?);
            if !self.eat(",") {
                break;
            }
        }
        self.close(close, open)?;
        Ok(items)
    }

    fn braced(&mut self, position: usize) -> Result<Node, Failure> {
        self.index += 1;
        if self.eat("}") {
            return Ok(Node {
                expr: Expr::Dict(Vec::new()),
                position,
            });
        }
        if !self.at_operator("**") {
            let first: Node = self.starred_or_expression()?;
            if !self.eat(":") {
                let mut items: Vec<Node> = vec![first];
                if self.eat(",") {
                    items.extend(self.items("}", position)?);
                } else {
                    self.close("}", position)?;
                }
                return Ok(Node {
                    expr: Expr::Set(items),
                    position,
                });
            }
            let value: Node = self.expression()?;
            let mut pairs: Vec<(Option<Node>, Node)> = vec![(Some(first), value)];
            if self.eat(",") {
                pairs.extend(self.pairs(position)?);
            } else {
                self.close("}", position)?;
            }
            return Ok(Node {
                expr: Expr::Dict(pairs),
                position,
            });
        }
        let pairs: Vec<(Option<Node>, Node)> = self.pairs(position)?;
        Ok(Node {
            expr: Expr::Dict(pairs),
            position,
        })
    }

    fn pairs(&mut self, open: usize) -> Result<Vec<(Option<Node>, Node)>, Failure> {
        let mut pairs: Vec<(Option<Node>, Node)> = Vec::new();
        while !self.at_operator("}") && !matches!(self.peek().kind, TokenKind::End) {
            if self.eat("**") {
                pairs.push((None, self.expression()?));
            } else {
                let key: Node = self.expression()?;
                if !self.eat(":") {
                    return Err(self.unexpected());
                }
                pairs.push((Some(key), self.expression()?));
            }
            if !self.eat(",") {
                break;
            }
        }
        self.close("}", open)?;
        Ok(pairs)
    }
}
