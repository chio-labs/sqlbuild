//! Batched tokenization for authored SQLBuild MODEL headers.

use rayon::iter::{IntoParallelRefIterator, ParallelIterator};
use rayon::{ThreadPool, ThreadPoolBuilder};

use crate::compiler::models::AuthoredValue;
use crate::constants::{
    CLOSE_PAREN, COLUMNS_KEY, CONSTANT_CALL, INLINE_SQL_HOOK, OPEN_PAREN, OUTSIDE_KEY, SQL_HOOK,
    THRESHOLDS_KEY, TYPE_KEY,
};

pub(crate) const MAX_TOKENIZER_WORKERS: usize = 4;
pub(crate) const TOKENIZER_WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

pub(crate) const END_TOKEN: u8 = 0;
pub(crate) const WORD_TOKEN: u8 = 1;
pub(crate) const STRING_TOKEN: u8 = 2;
pub(crate) const SYMBOL_TOKEN: u8 = 3;

pub(crate) type HeaderToken = (u8, String, usize);
pub(crate) type HeaderColumnOffset = (String, usize, usize);
pub(crate) type HeaderParseResult = (
    Option<AuthoredValue>,
    Option<Vec<HeaderColumnOffset>>,
    Option<String>,
);

pub(crate) fn parse_batch(headers: &[String]) -> Result<Vec<HeaderParseResult>, String> {
    let pool = build_tokenizer_pool(headers.len())?;
    Ok(pool.install(|| {
        headers
            .par_iter()
            .map(
                |header| match tokenize(header).and_then(HeaderParser::parse) {
                    Ok((value, offsets)) => (Some(value), Some(offsets), None),
                    Err(error) => (None, None, Some(error)),
                },
            )
            .collect()
    }))
}

pub(crate) fn tokenize_one(header: &str) -> Result<Vec<HeaderToken>, String> {
    tokenize(header)
}

pub(crate) fn build_tokenizer_pool(header_count: usize) -> Result<ThreadPool, String> {
    ThreadPoolBuilder::new()
        .num_threads(header_count.clamp(1, MAX_TOKENIZER_WORKERS))
        .stack_size(TOKENIZER_WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())
}

struct HeaderParser {
    tokens: Vec<HeaderToken>,
    index: usize,
    column_offsets: Vec<HeaderColumnOffset>,
}

#[derive(Clone, Copy, Default)]
struct ParseValueOptions {
    threshold_policy: bool,
    allow_outside: bool,
    nested_columns: bool,
    nested_metadata: bool,
    record_nested_columns: bool,
}

#[derive(Clone, Copy, Default)]
struct ParseMapOptions<'a> {
    end: Option<&'a str>,
    threshold_policy: bool,
    allow_outside: bool,
    column_entries: bool,
    column_metadata: bool,
    record_column_entries: bool,
}

impl HeaderParser {
    fn parse(tokens: Vec<HeaderToken>) -> Result<(AuthoredValue, Vec<HeaderColumnOffset>), String> {
        let mut parser = Self {
            tokens,
            index: 0,
            column_offsets: Vec::new(),
        };
        let value = if parser.peek().0 == END_TOKEN {
            AuthoredValue::Map(Vec::new())
        } else {
            AuthoredValue::Map(parser.parse_map(ParseMapOptions::default())?)
        };
        parser.expect_end()?;
        Ok((value, parser.column_offsets))
    }

    fn parse_map(
        &mut self,
        options: ParseMapOptions<'_>,
    ) -> Result<Vec<(String, AuthoredValue)>, String> {
        let mut values: Vec<(String, AuthoredValue)> = Vec::new();
        while !self.at_end_symbol(options.end) {
            if self.match_symbol(",") {
                continue;
            }
            let key_token = self.peek().clone();
            let key = self.consume_key()?;
            if values.iter().any(|(existing, _)| existing == &key) {
                return Err(format!("duplicate key '{key}'"));
            }
            if self.match_symbol(":") {
                return Err(format!(
                    "unexpected ':' after key '{key}'; use SQLBuild syntax '{key} value'"
                ));
            }
            if self.at_end_symbol(options.end) || self.peek().0 == END_TOKEN {
                return Err(format!(
                    "unexpected token '{key}' without a value; quote values with spaces"
                ));
            }
            if options.column_entries && options.record_column_entries {
                self.column_offsets
                    .push((key.clone(), key_token.2, key.chars().count()));
            }
            let value = if options.allow_outside && key == OUTSIDE_KEY {
                self.parse_outside()?
            } else if matches!(key.as_str(), "pre_hooks" | "post_hooks") {
                self.parse_hook_field(&key)?
            } else if options.column_metadata && key == TYPE_KEY {
                self.parse_type()?
            } else {
                self.parse_value(ParseValueOptions {
                    threshold_policy: key == THRESHOLDS_KEY,
                    allow_outside: options.threshold_policy
                        && matches!(key.as_str(), "warn" | "error"),
                    nested_columns: key == COLUMNS_KEY,
                    nested_metadata: options.column_entries,
                    record_nested_columns: options.end.is_none() && key == COLUMNS_KEY,
                })?
            };
            values.push((key, value));
            self.match_symbol(",");
        }
        if let Some(symbol) = options.end {
            self.consume_symbol(symbol)?;
        }
        Ok(values)
    }

    fn parse_outside(&mut self) -> Result<AuthoredValue, String> {
        let lower = self.parse_value(ParseValueOptions::default())?;
        if self.at_end_symbol(Some(")")) {
            return Err("outside threshold requires lower and upper values".to_owned());
        }
        let upper = self.parse_value(ParseValueOptions::default())?;
        Ok(AuthoredValue::Tuple(vec![lower, upper]))
    }

    fn parse_type(&mut self) -> Result<AuthoredValue, String> {
        let token = self.peek().clone();
        if token.0 != WORD_TOKEN
            || self
                .tokens
                .get(self.index + 1)
                .is_none_or(|next| next.0 != SYMBOL_TOKEN || next.1 != OPEN_PAREN)
        {
            return self.parse_value(ParseValueOptions::default());
        }
        let mut value = self.advance().1.clone();
        value.push_str(&self.advance().1);
        let mut depth = 1_usize;
        while depth > 0 {
            let parameter = self.peek().clone();
            if parameter.0 == END_TOKEN {
                return Err(format!("unterminated SQL type at position {}", token.2));
            }
            if parameter.0 == STRING_TOKEN {
                return Err(format!(
                    "quoted SQL type parameters require the whole type to be quoted at position {}",
                    parameter.2
                ));
            }
            self.advance();
            value.push_str(&parameter.1);
            if parameter.0 == SYMBOL_TOKEN && parameter.1 == OPEN_PAREN {
                depth += 1;
            } else if parameter.0 == SYMBOL_TOKEN && parameter.1 == CLOSE_PAREN {
                depth -= 1;
            }
        }
        Ok(AuthoredValue::String(value))
    }

    fn parse_value(&mut self, options: ParseValueOptions) -> Result<AuthoredValue, String> {
        let token = self.peek().clone();
        if token.0 == STRING_TOKEN {
            self.advance();
            return Ok(AuthoredValue::String(token.1));
        }
        if token.0 == WORD_TOKEN {
            self.advance();
            if self.peek().0 == SYMBOL_TOKEN && self.peek().1 == OPEN_PAREN {
                self.advance();
                if matches!(token.1.as_str(), "__ref" | "__seed" | "__source") {
                    return self.parse_relation(&token.1);
                }
                if matches!(token.1.as_str(), "inline_sql" | "sql" | "python") {
                    return self.parse_hook(&token.1);
                }
                if token.1 == CONSTANT_CALL {
                    return Ok(AuthoredValue::TypedConstant(self.parse_map(
                        ParseMapOptions {
                            end: Some(")"),
                            ..ParseMapOptions::default()
                        },
                    )?));
                }
                return Ok(AuthoredValue::Map(vec![(
                    token.1,
                    AuthoredValue::Map(self.parse_map(ParseMapOptions {
                        end: Some(")"),
                        threshold_policy: options.threshold_policy,
                        allow_outside: options.allow_outside,
                        ..ParseMapOptions::default()
                    })?),
                )]));
            }
            return Ok(parse_word(token.1));
        }
        if self.match_symbol("[") {
            return Ok(AuthoredValue::List(self.parse_sequence("]")?));
        }
        if self.match_symbol("{") {
            return Ok(AuthoredValue::Set(self.parse_sequence("}")?));
        }
        if self.match_symbol("(") {
            return Ok(AuthoredValue::Map(self.parse_map(ParseMapOptions {
                end: Some(")"),
                threshold_policy: options.threshold_policy,
                allow_outside: options.allow_outside,
                column_entries: options.nested_columns,
                column_metadata: options.nested_metadata,
                record_column_entries: options.record_nested_columns,
            })?));
        }
        Err(format!("expected value at position {}", token.2))
    }

    fn parse_sequence(&mut self, end: &str) -> Result<Vec<AuthoredValue>, String> {
        let mut values: Vec<AuthoredValue> = Vec::new();
        while !self.at_end_symbol(Some(end)) {
            if self.match_symbol(",") {
                continue;
            }
            values.push(self.parse_value(ParseValueOptions::default())?);
            self.match_symbol(",");
        }
        self.consume_symbol(end)?;
        Ok(values)
    }

    fn parse_hook_field(&mut self, field: &str) -> Result<AuthoredValue, String> {
        if !self.match_symbol("[") {
            return Err(format!(
                "{field} must be a list of typed inline_sql(...), sql(...), or python(...) hook entries at position {}",
                self.peek().2
            ));
        }
        let mut values: Vec<AuthoredValue> = Vec::new();
        while !self.at_end_symbol(Some("]")) {
            if self.match_symbol(",") {
                continue;
            }
            values.push(self.parse_hook_entry(field)?);
            self.match_symbol(",");
        }
        self.consume_symbol("]")?;
        Ok(AuthoredValue::List(values))
    }

    fn parse_hook_entry(&mut self, field: &str) -> Result<AuthoredValue, String> {
        let token = self.peek().clone();
        if token.0 == STRING_TOKEN {
            self.advance();
            return Ok(AuthoredValue::String(token.1));
        }
        let error = || {
            format!(
                "{field} entries must use typed inline_sql(...), sql(...), or python(...) hook syntax"
            )
        };
        if token.0 != WORD_TOKEN {
            return Err(error());
        }
        self.advance();
        if self.peek().0 != SYMBOL_TOKEN || self.peek().1 != OPEN_PAREN {
            return Err(error());
        }
        self.advance();
        if !matches!(token.1.as_str(), "inline_sql" | "sql" | "python") {
            return Err(error());
        }
        self.parse_hook(&token.1)
    }

    fn parse_relation(&mut self, name: &str) -> Result<AuthoredValue, String> {
        let token = self.peek().clone();
        if token.0 != STRING_TOKEN {
            return Err(format!(
                "{name}(...) requires a double-quoted relation name"
            ));
        }
        self.advance();
        self.consume_symbol(")")?;
        Ok(AuthoredValue::String(format!(
            "{name}(\"{}\")",
            token.1.replace('"', "\\\"")
        )))
    }

    fn parse_hook(&mut self, name: &str) -> Result<AuthoredValue, String> {
        if name == INLINE_SQL_HOOK {
            let token = self.peek().clone();
            if token.0 != STRING_TOKEN {
                return Err("inline_sql(...) requires a quoted SQL string".to_owned());
            }
            self.advance();
            if self.match_symbol(",") {
                return Err("inline_sql(...) does not accept additional arguments".to_owned());
            }
            self.consume_symbol(")")?;
            return Ok(AuthoredValue::InlineSqlHook(token.1));
        }
        let token = self.peek().clone();
        if token.0 != STRING_TOKEN {
            return Err(format!("{name}(...) requires a quoted hook name"));
        }
        self.advance();
        if token.1.chars().all(is_python_whitespace) {
            return Err(format!("{name}(...) requires a non-empty hook name"));
        }
        let kwargs = self.parse_hook_kwargs()?;
        if name == SQL_HOOK {
            Ok(AuthoredValue::NamedSqlHook(token.1, kwargs))
        } else {
            Ok(AuthoredValue::PythonHook(token.1, kwargs))
        }
    }

    fn parse_hook_kwargs(&mut self) -> Result<Vec<(String, AuthoredValue)>, String> {
        let mut values: Vec<(String, AuthoredValue)> = Vec::new();
        while self.match_symbol(",") {
            if self.at_end_symbol(Some(")")) {
                break;
            }
            let key = self.consume_key()?;
            if values.iter().any(|(existing, _)| existing == &key) {
                return Err(format!("duplicate hook argument '{key}'"));
            }
            self.consume_symbol(":")?;
            values.push((key, self.parse_value(ParseValueOptions::default())?));
        }
        self.consume_symbol(")")?;
        Ok(values)
    }

    fn consume_key(&mut self) -> Result<String, String> {
        let token = self.peek().clone();
        if token.0 != WORD_TOKEN {
            return Err(format!("expected key at position {}", token.2));
        }
        self.advance();
        Ok(token.1)
    }

    fn at_end_symbol(&self, symbol: Option<&str>) -> bool {
        let token = self.peek();
        symbol.map_or(token.0 == END_TOKEN, |expected| {
            token.0 == SYMBOL_TOKEN && token.1 == expected
        })
    }

    fn match_symbol(&mut self, symbol: &str) -> bool {
        if self.peek().0 == SYMBOL_TOKEN && self.peek().1 == symbol {
            self.advance();
            true
        } else {
            false
        }
    }

    fn consume_symbol(&mut self, symbol: &str) -> Result<(), String> {
        if self.match_symbol(symbol) {
            Ok(())
        } else {
            Err(format!("expected '{symbol}' at position {}", self.peek().2))
        }
    }

    fn expect_end(&self) -> Result<(), String> {
        let token = self.peek();
        if token.0 == END_TOKEN {
            Ok(())
        } else {
            Err(format!(
                "unexpected token '{}' at position {}",
                token.1, token.2
            ))
        }
    }

    fn peek(&self) -> &HeaderToken {
        &self.tokens[self.index]
    }

    fn advance(&mut self) -> &HeaderToken {
        let token = &self.tokens[self.index];
        self.index += 1;
        token
    }
}

fn parse_word(value: String) -> AuthoredValue {
    match value.as_str() {
        "true" => AuthoredValue::Boolean(true),
        "false" => AuthoredValue::Boolean(false),
        "null" => AuthoredValue::Null,
        _ => AuthoredValue::BareWord(value),
    }
}

fn tokenize(header: &str) -> Result<Vec<HeaderToken>, String> {
    let characters: Vec<char> = header.chars().collect();
    let mut tokens: Vec<HeaderToken> = Vec::new();
    let mut index = 0;
    while index < characters.len() {
        let character = characters[index];
        if is_python_whitespace(character) {
            index += 1;
            continue;
        }
        if starts_template(&characters, index) {
            let template_end = find_character(&characters, '}', index + 2)
                .ok_or_else(|| format!("unterminated template value at position {index}"))?;
            tokens.push((
                WORD_TOKEN,
                characters[index..=template_end].iter().collect(),
                index,
            ));
            index = template_end + 1;
            continue;
        }
        if is_symbol(character) || character == ':' {
            tokens.push((SYMBOL_TOKEN, character.to_string(), index));
            index += 1;
            continue;
        }
        if matches!(character, '\'' | '"') {
            let (value, next_index) = read_quoted_string(&characters, index)?;
            tokens.push((STRING_TOKEN, value, index));
            index = next_index;
            continue;
        }

        let start = index;
        while index < characters.len() {
            if starts_template(&characters, index) {
                let template_end = find_character(&characters, '}', index + 2)
                    .ok_or_else(|| format!("unterminated template value at position {index}"))?;
                index = template_end + 1;
                continue;
            }
            let next = characters[index];
            if is_python_whitespace(next) || is_symbol(next) || next == ':' {
                break;
            }
            if matches!(next, '\'' | '"') {
                let quote_name = if next == '\'' { "single" } else { "double" };
                return Err(format!(
                    "unexpected {quote_name} quote inside bare value at position {index}; quote the whole value"
                ));
            }
            index += 1;
        }
        if start == index {
            return Err(format!(
                "unexpected character '{character}' at position {start}"
            ));
        }
        tokens.push((WORD_TOKEN, characters[start..index].iter().collect(), start));
    }
    tokens.push((END_TOKEN, String::new(), characters.len()));
    Ok(tokens)
}

fn read_quoted_string(characters: &[char], start: usize) -> Result<(String, usize), String> {
    let quote = characters[start];
    let quote_name = if quote == '\'' { "single" } else { "double" };
    let mut value = String::new();
    let mut index = start + 1;
    while index < characters.len() {
        let character = characters[index];
        if character == '\\' {
            if index + 1 >= characters.len() {
                return Err(format!("unterminated escape at position {index}"));
            }
            value.push(characters[index + 1]);
            index += 2;
            continue;
        }
        if character == quote {
            return Ok((value, index + 1));
        }
        value.push(character);
        index += 1;
    }
    Err(format!(
        "unterminated {quote_name}-quoted string at position {start}"
    ))
}

fn starts_template(characters: &[char], index: usize) -> bool {
    characters.get(index) == Some(&'$') && characters.get(index + 1) == Some(&'{')
}

fn find_character(characters: &[char], needle: char, start: usize) -> Option<usize> {
    characters[start..]
        .iter()
        .position(|character| *character == needle)
        .map(|offset| start + offset)
}

fn is_symbol(character: char) -> bool {
    matches!(character, '(' | ')' | '[' | ']' | '{' | '}' | ',')
}

fn is_python_whitespace(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{1c}'..='\u{1f}')
}
