//! The `MACRO (...)` header of a SQL macro file: description, typed arguments and result type.

use crate::sql_macros::_helpers::parsing::lexing::{
    Token, TokenKind, closing_token, line_column, tokens,
};
use crate::sql_macros::constants::{
    ANY_KEYWORD, ARGUMENTS_KEY, COLUMNS_KEYWORD, COMMA, CONST_KEYWORD, DEFAULT_KEYWORD,
    DESCRIPTION_KEY, ENUM_KEYWORD, HEADER_KEYWORD, INVALID_DEFINITION_CODE, LIST_KEYWORD,
    OF_KEYWORD, RAW_TYPE_NAMES, RELATION_COLUMN_MIN_TOKENS, RELATION_KEYWORD, RETURNS_KEY,
    SET_KEYWORD, TYPE_KEYWORD,
};
use crate::sql_macros::errors::LexError;
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{AnyFamily, ParameterKind, SqlMacroLocation, SqlMacroParameter};
use sqlbuild_sqltext::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE_HELP, DOUBLE_QUOTE_INSIDE_MESSAGE, SINGLE_QUOTE_INSIDE_HELP,
    SINGLE_QUOTE_INSIDE_MESSAGE, TRIPLE_QUOTE_INSIDE_HELP, TRIPLE_QUOTE_INSIDE_MESSAGE,
    UNCLOSED_TRIPLE_QUOTE_HELP, UNCLOSED_TRIPLE_QUOTE_MESSAGE,
};
use sqlbuild_sqltext::header_strings::main::prose_string::prose_string;

/// What the header declares and where the body starts.
pub(crate) struct Header {
    pub(crate) description: Option<String>,
    pub(crate) parameters: Vec<SqlMacroParameter>,
    pub(crate) returns: Option<String>,
    /// The argument named by `returns TYPE OF <argument>`, and its byte offset.
    pub(crate) returns_like: Option<(String, usize)>,
    /// Byte offset just past the header and its optional `;`.
    pub(crate) body_start: usize,
}

/// Parses one file's header, locating errors in the file.
pub(crate) struct HeaderParser<'a> {
    pub(crate) name: &'a str,
    pub(crate) path: &'a str,
    pub(crate) source: &'a str,
}

impl HeaderParser<'_> {
    fn error(&self, offset: usize, message: impl Into<String>) -> SqlMacroError {
        let (line, column) = line_column(self.source, offset);
        SqlMacroError::new(INVALID_DEFINITION_CODE, message).at(SqlMacroLocation {
            path: self.path.to_owned(),
            line,
            column,
        })
    }

    pub(crate) fn parse(&self) -> Result<Header, SqlMacroError> {
        let source: &str = self.source;
        let scanned: Vec<Token> = tokens(source).map_err(|error| match error {
            LexError::UnclosedQuote(at) => self.error(at, "unclosed quote in SQL macro file"),
            LexError::UnclosedComment(at) => self.error(at, "unclosed comment in SQL macro file"),
            LexError::QuoteInside(at) => self
                .error(at, DOUBLE_QUOTE_INSIDE_MESSAGE)
                .helped(DOUBLE_QUOTE_INSIDE_HELP),
            LexError::SingleQuoteInside(at) => self
                .error(at, SINGLE_QUOTE_INSIDE_MESSAGE)
                .helped(SINGLE_QUOTE_INSIDE_HELP),
            LexError::TripleQuoteInside(at) => self
                .error(at, TRIPLE_QUOTE_INSIDE_MESSAGE)
                .helped(TRIPLE_QUOTE_INSIDE_HELP),
            LexError::UnclosedTripleQuote(at) => self
                .error(at, UNCLOSED_TRIPLE_QUOTE_MESSAGE)
                .helped(UNCLOSED_TRIPLE_QUOTE_HELP),
        })?;
        let starts_with_header: bool = scanned
            .first()
            .is_some_and(|token| token.is_word(source, HEADER_KEYWORD))
            && scanned.get(1).is_some_and(|token| token.is(source, "("));
        if !starts_with_header {
            let at: usize = scanned.first().map_or(0, |token| token.start);
            return Err(self
                .error(at, format!("SQL macro file {} must start with a MACRO (...) header", self.path))
                .helped("start the file with MACRO (description \"...\", arguments (...)); then the body"));
        }
        let close: usize = closing_token(source, &scanned, 1)
            .ok_or_else(|| self.error(scanned[1].start, "MACRO header is not closed"))?;
        let mut body_start: usize = scanned[close].end;
        if let Some(semicolon) = scanned.get(close + 1)
            && semicolon.is(source, ";")
        {
            body_start = semicolon.end;
        }
        let mut header: Header = Header {
            description: None,
            parameters: Vec::new(),
            returns: None,
            returns_like: None,
            body_start,
        };
        for entry in split_top_level(source, &scanned[2..close]) {
            header = self.entry(entry, header)?;
        }
        Ok(header)
    }

    fn entry(&self, entry: &[Token], header: Header) -> Result<Header, SqlMacroError> {
        let mut header: Header = header;
        let source: &str = self.source;
        let Some((key, value)) = entry.split_first() else {
            return Ok(header);
        };
        let key_text: String = key.text(source).to_ascii_lowercase();
        if key.kind != TokenKind::Word {
            return Err(self.error(
                key.start,
                format!("unexpected {} in MACRO header", key.text(source)),
            ));
        }
        match key_text.as_str() {
            DESCRIPTION_KEY => match value {
                [text] if matches!(text.kind, TokenKind::Quoted | TokenKind::Text) => {
                    header.description = Some(self.description(text)?);
                    Ok(header)
                }
                _ => Err(self.error(key.start, "description must be one quoted string")),
            },
            ARGUMENTS_KEY => {
                let close: Option<usize> = value
                    .first()
                    .filter(|open| open.is(source, "("))
                    .and_then(|_| closing_token(source, value, 0));
                match close {
                    Some(close) if close == value.len() - 1 => {
                        for parameter in split_top_level(source, &value[1..close]) {
                            let parsed: SqlMacroParameter = self.parameter(parameter)?;
                            if header
                                .parameters
                                .iter()
                                .any(|known| known.name.eq_ignore_ascii_case(&parsed.name))
                            {
                                return Err(self.error(
                                    parameter[0].start,
                                    format!(
                                        "macro {}() declares argument {} twice",
                                        self.name, parsed.name
                                    ),
                                ));
                            }
                            header.parameters.push(parsed);
                        }
                        Ok(header)
                    }
                    _ => Err(self.error(key.start, "arguments must be a parenthesised list")),
                }
            }
            RETURNS_KEY => {
                if value.is_empty() {
                    return Err(self.error(key.start, "returns needs a SQL type"));
                }
                if let [type_word, of, argument] = value
                    && type_word.is_word(source, TYPE_KEYWORD)
                    && of.is_word(source, OF_KEYWORD)
                {
                    if argument.kind != TokenKind::Word {
                        return Err(self.error(
                            argument.start,
                            "returns TYPE OF needs an argument name, such as returns TYPE OF value",
                        ));
                    }
                    header.returns_like = Some((argument.text(source).to_owned(), argument.start));
                    return Ok(header);
                }
                header.returns = Some(type_text(source, value));
                Ok(header)
            }
            _ => Err(self
                .error(
                    key.start,
                    format!("unknown MACRO header key {}", key.text(source)),
                )
                .helped("a MACRO header accepts description, arguments and returns")),
        }
    }

    /// The folded prose of the description string `text`, which lexing found well quoted.
    fn description(&self, text: &Token) -> Result<String, SqlMacroError> {
        let raw: Vec<char> = text.text(self.source).chars().collect();
        prose_string(&raw, 0)
            .map(|prose| prose.value)
            .map_err(|_| self.error(text.start, "description must be one quoted string"))
    }

    fn parameter(&self, tokens: &[Token]) -> Result<SqlMacroParameter, SqlMacroError> {
        let source: &str = self.source;
        let name: &Token = &tokens[0];
        if name.kind != TokenKind::Word {
            return Err(self.error(
                name.start,
                format!("expected an argument name, found {}", name.text(source)),
            ));
        }
        let name_text: String = name.text(source).to_owned();
        let default_at: Option<usize> = tokens
            .iter()
            .position(|token| token.is_word(source, DEFAULT_KEYWORD));
        let (type_tokens, default) = match default_at {
            Some(at) => {
                let default_tokens: &[Token] = &tokens[at + 1..];
                let (Some(first), Some(last)) = (default_tokens.first(), default_tokens.last())
                else {
                    return Err(self.error(
                        tokens[at].start,
                        format!("DEFAULT of argument {name_text} needs a value"),
                    ));
                };
                (
                    &tokens[1..at],
                    Some(source[first.start..last.end].to_owned()),
                )
            }
            None => (&tokens[1..], None),
        };
        let kind: ParameterKind = self.kind(&name_text, name, type_tokens)?;
        if default.is_some() && matches!(kind, ParameterKind::Relation { .. }) {
            return Err(self
                .error(
                    name.start,
                    format!("argument {name_text} is a RELATION and cannot have a DEFAULT"),
                )
                .helped("relations are always passed explicitly"));
        }
        let (line, column) = line_column(source, name.start);
        Ok(SqlMacroParameter {
            name: name_text,
            kind,
            default,
            line,
            column,
        })
    }

    fn kind(
        &self,
        name: &str,
        name_token: &Token,
        tokens: &[Token],
    ) -> Result<ParameterKind, SqlMacroError> {
        let source: &str = self.source;
        let untyped = || {
            self.error(
                name_token.start,
                format!("argument {name} of macro {}() has no type", self.name),
            )
            .helped("give every argument a type, such as amount BIGINT, places INT CONST or src RELATION (id BIGINT, keys COLUMNS)")
        };
        let Some(first) = tokens.first() else {
            return Err(untyped());
        };
        if first.is_word(source, RELATION_KEYWORD) {
            let close: Option<usize> = tokens
                .get(1)
                .filter(|open| open.is(source, "("))
                .and_then(|_| closing_token(source, tokens, 1));
            let Some(close) = close.filter(|close| *close == tokens.len() - 1) else {
                return Err(self.error(first.start, format!("argument {name} RELATION needs a parenthesised column list, such as RELATION (id BIGINT)")));
            };
            let mut columns: Vec<(String, String)> = Vec::new();
            let mut groups: Vec<String> = Vec::new();
            for column in split_top_level(source, &tokens[2..close]) {
                let column_name: &Token = &column[0];
                if !matches!(column_name.kind, TokenKind::Word | TokenKind::Quoted)
                    || column.len() < RELATION_COLUMN_MIN_TOKENS
                {
                    return Err(self.error(
                        column_name.start,
                        format!("each slot of RELATION argument {name} needs a name and a type or COLUMNS"),
                    ));
                }
                let slot: String = unquoted(column_name.text(source));
                if columns
                    .iter()
                    .map(|(known, _)| known)
                    .chain(groups.iter())
                    .any(|known| known.eq_ignore_ascii_case(&slot))
                {
                    return Err(self.error(
                        column_name.start,
                        format!("RELATION argument {name} declares slot {slot} twice"),
                    ));
                }
                if column[1].is_word(source, COLUMNS_KEYWORD) {
                    if let Some(extra) = column.get(2) {
                        return Err(self
                            .error(extra.start, format!("slot {name}.{slot} COLUMNS takes nothing after it; a COLUMNS slot is untyped and each passed column keeps its own type"))
                            .helped(format!("declare it {slot} COLUMNS")));
                    }
                    groups.push(slot);
                    continue;
                }
                columns.push((slot, self.sql_type(name, &column[1..], column_name)?));
            }
            if columns.is_empty() && groups.is_empty() {
                return Err(self.error(
                    first.start,
                    format!("RELATION argument {name} declares no columns"),
                ));
            }
            return Ok(ParameterKind::Relation { columns, groups });
        }
        if first.is_word(source, ENUM_KEYWORD) {
            return match tokens {
                [_, enum_name] if matches!(enum_name.kind, TokenKind::Word | TokenKind::Quoted) => {
                    Ok(ParameterKind::Enum {
                        name: unquoted(enum_name.text(source)),
                    })
                }
                _ => Err(self.error(
                    first.start,
                    format!("argument {name} ENUM needs an enum name, such as ENUM order_status"),
                )),
            };
        }
        if first.is_word(source, ANY_KEYWORD) {
            let Some(after) = tokens.get(1) else {
                return Ok(ParameterKind::Any { family: None });
            };
            let family: Option<AnyFamily> = AnyFamily::ALL
                .into_iter()
                .find(|family| after.is_word(source, family.keyword()));
            if let Some(family) = family {
                let Some(extra) = tokens.get(2) else {
                    return Ok(ParameterKind::Any {
                        family: Some(family),
                    });
                };
                return Err(self
                    .error(extra.start, format!("argument {name} ANY {} takes nothing after it; CONST, LIST and SET are not supported for ANY families", family.keyword()))
                    .helped(format!("declare it {name} ANY {}, or give it a SQL type", family.keyword())));
            }
            if after.is_word(source, CONST_KEYWORD) {
                return Err(self
                    .error(after.start, format!("argument {name} ANY CONST: a CONST argument needs a type its values are checked against"))
                    .helped(format!("declare it with the type of its values, such as {name} VARCHAR CONST")));
            }
            return Err(self
                .error(after.start, format!("argument {name} ANY takes nothing after it but NUMERIC, TEXT or TEMPORAL; ANY accepts any scalar expression"))
                .helped(format!("declare it {name} ANY, or {name} ANY NUMERIC, ANY TEXT or ANY TEMPORAL for one type family, or give it a SQL type")));
        }
        if first.is_word(source, LIST_KEYWORD) || first.is_word(source, SET_KEYWORD) {
            let set: bool = first.is_word(source, SET_KEYWORD);
            let keyword: String = first.text(source).to_ascii_uppercase();
            let element: &[Token] = &tokens[1..];
            if element
                .first()
                .is_some_and(|first| first.is_word(source, ANY_KEYWORD))
            {
                return Err(self
                    .error(
                        element[0].start,
                        format!("argument {name} {keyword} ANY: ANY is for scalar arguments only"),
                    )
                    .helped(format!(
                        "declare the element type, such as {name} {keyword} VARCHAR"
                    )));
            }
            if let Some((last, element)) = element.split_last()
                && last.is_word(source, CONST_KEYWORD)
            {
                let element_type: String = type_text(source, element);
                return Err(self
                    .error(last.start, format!("argument {name} {keyword} {element_type} CONST: a {keyword} argument is always known at compile time, so it takes no CONST"))
                    .helped(format!("declare it {name} {keyword} {element_type}")));
            }
            return Ok(ParameterKind::Collection {
                set,
                data_type: self.sql_type(name, element, first)?,
            });
        }
        if let Some((last, data_type)) = tokens.split_last()
            && last.is_word(source, CONST_KEYWORD)
        {
            let data_type: String = self.sql_type(name, data_type, name_token)?;
            if is_array_type(&data_type) {
                return Err(self
                    .error(last.start, format!("argument {name} {data_type} CONST: CONST is for scalar types only"))
                    .helped(format!("declare it {name} LIST {} for a list known at compile time, or {name} {data_type} for a runtime array", array_element(&data_type))));
            }
            return Ok(ParameterKind::Constant { data_type });
        }
        Ok(ParameterKind::Expression {
            data_type: self.sql_type(name, tokens, name_token)?,
        })
    }

    fn sql_type(&self, name: &str, tokens: &[Token], at: &Token) -> Result<String, SqlMacroError> {
        let source: &str = self.source;
        let Some(first) = tokens.first() else {
            return Err(self.error(
                at.start,
                format!("argument {name} of macro {}() has no type", self.name),
            ));
        };
        if first.kind != TokenKind::Word {
            return Err(self.error(
                first.start,
                format!(
                    "expected a SQL type for argument {name}, found {}",
                    first.text(source)
                ),
            ));
        }
        if RAW_TYPE_NAMES
            .iter()
            .any(|raw| first.text(source).eq_ignore_ascii_case(raw))
            && tokens.len() == 1
        {
            return Err(self
                .error(first.start, format!("argument {name} of macro {}() is raw text; SQL macro arguments are typed SQL", self.name))
                .helped("use a SQL type such as BIGINT, a CONST type, an ENUM or a RELATION"));
        }
        Ok(type_text(source, tokens))
    }
}

/// Token slices between top-level commas, empty slices dropped.
pub(crate) fn split_top_level<'t>(source: &str, tokens: &'t [Token]) -> Vec<&'t [Token]> {
    let mut parts: Vec<&'t [Token]> = Vec::new();
    let mut depth: usize = 0;
    let mut start: usize = 0;
    for (index, token) in tokens.iter().enumerate() {
        if token.kind != TokenKind::Punct {
            continue;
        }
        match token.text(source) {
            "(" | "[" | "{" => depth += 1,
            ")" | "]" | "}" => depth = depth.saturating_sub(1),
            "," if depth == 0 => {
                if index > start {
                    parts.push(&tokens[start..index]);
                }
                start = index + 1;
            }
            _ => {}
        }
    }
    if tokens.len() > start {
        parts.push(&tokens[start..]);
    }
    parts
}

/// A SQL type as messages show it: keywords upper-cased, arguments as `(18, 2)`.
pub(crate) fn type_text(source: &str, tokens: &[Token]) -> String {
    let mut text: String = String::new();
    let mut previous_word: bool = false;
    for token in tokens {
        let piece: &str = token.text(source);
        match token.kind {
            TokenKind::Word => {
                if previous_word {
                    text.push(' ');
                }
                text.push_str(&piece.to_ascii_uppercase());
                previous_word = true;
            }
            TokenKind::Punct if piece == COMMA => {
                text.push_str(", ");
                previous_word = false;
            }
            _ => {
                text.push_str(piece);
                previous_word = token.kind == TokenKind::Number;
            }
        }
    }
    text
}

/// A quoted string's text without its quotes, doubled quotes unescaped.
pub(crate) fn unquoted(text: &str) -> String {
    let Some(quote) = text
        .chars()
        .next()
        .filter(|quote| matches!(quote, '"' | '\'' | '`'))
    else {
        return text.to_owned();
    };
    let inner: &str = &text[1..text.len().saturating_sub(1).max(1)];
    let doubled: String = format!("{quote}{quote}");
    inner.replace(&doubled, &quote.to_string())
}

/// Whether a declared type is an array, map or struct rather than a scalar.
fn is_array_type(data_type: &str) -> bool {
    let upper: String = data_type.to_ascii_uppercase();
    upper.ends_with(']')
        || ["ARRAY", "LIST", "MAP", "STRUCT", "OBJECT", "VARIANT"]
            .iter()
            .any(|composite| {
                upper == *composite
                    || upper.starts_with(&format!("{composite}<"))
                    || upper.starts_with(&format!("{composite}("))
            })
}

/// The element type of an array type such as `VARCHAR[]` or `ARRAY<VARCHAR>`.
fn array_element(data_type: &str) -> String {
    if let Some(element) = data_type.strip_suffix("[]") {
        return element.trim().to_owned();
    }
    data_type
        .find(['<', '('])
        .map(|open| {
            data_type[open + 1..data_type.len().saturating_sub(1)]
                .trim()
                .to_owned()
        })
        .filter(|element| !element.is_empty())
        .unwrap_or_else(|| "<type>".to_owned())
}
