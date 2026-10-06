//! Minimal parser for macro call arguments: Python literals plus nested-call placeholders.

#[derive(Clone, Debug, PartialEq)]
pub enum Lit {
    Str(String),
    Int(i64),
    Float(String),
    Bool(bool),
    None,
    List(Vec<Lit>),
    Tuple(Vec<Lit>),
    Dict(Vec<(Lit, Lit)>),
    /// Result of a nested macro call, by call key.
    Nested(String),
}

impl Lit {
    /// Canonical text used inside memo keys.
    pub fn key(&self, out: &mut String) {
        use std::fmt::Write;
        match self {
            Self::Str(value) => {
                let _ = write!(out, "s{}:{value}", value.len());
            }
            Self::Int(value) => {
                let _ = write!(out, "i{value}");
            }
            Self::Float(value) => {
                let _ = write!(out, "f{value}");
            }
            Self::Bool(value) => {
                let _ = write!(out, "b{value}");
            }
            Self::None => out.push('n'),
            Self::Nested(key) => {
                let _ = write!(out, "m{}:{key}", key.len());
            }
            Self::List(items) | Self::Tuple(items) => {
                out.push(if matches!(self, Self::List(_)) {
                    '['
                } else {
                    '('
                });
                for item in items {
                    item.key(out);
                    out.push(',');
                }
                out.push(']');
            }
            Self::Dict(items) => {
                out.push('{');
                for (key, value) in items {
                    key.key(out);
                    out.push(':');
                    value.key(out);
                    out.push(',');
                }
                out.push('}');
            }
        }
    }
}

pub struct Args {
    pub positional: Vec<Lit>,
    pub keywords: Vec<(String, Lit)>,
}

pub struct Parser<'a> {
    text: &'a str,
    bytes: &'a [u8],
    index: usize,
    /// Placeholder name -> nested call key.
    placeholders: &'a [(String, String)],
}

pub type ParseResult<T> = Result<T, String>;

impl<'a> Parser<'a> {
    pub fn parse_args(text: &'a str, placeholders: &'a [(String, String)]) -> ParseResult<Args> {
        let mut parser = Self {
            text,
            bytes: text.as_bytes(),
            index: 0,
            placeholders,
        };
        let mut args = Args {
            positional: Vec::new(),
            keywords: Vec::new(),
        };
        loop {
            parser.ws();
            if parser.index >= parser.bytes.len() {
                break;
            }
            let save = parser.index;
            if let Some(name) = parser.ident() {
                parser.ws();
                if parser.peek() == Some(b'=') && parser.bytes.get(parser.index + 1) != Some(&b'=')
                {
                    parser.index += 1;
                    let value = parser.value()?;
                    args.keywords.push((name, value));
                    parser.ws();
                    if !parser.comma_or_end(None)? {
                        break;
                    }
                    continue;
                }
                parser.index = save;
            }
            let value = parser.value()?;
            if !args.keywords.is_empty() {
                return Err("positional argument after keyword".into());
            }
            args.positional.push(value);
            parser.ws();
            if !parser.comma_or_end(None)? {
                break;
            }
        }
        Ok(args)
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.index).copied()
    }

    fn ws(&mut self) {
        loop {
            while self.peek().is_some_and(|b| b.is_ascii_whitespace()) {
                self.index += 1;
            }
            if self.peek() == Some(b'#') {
                while self.peek().is_some_and(|b| b != b'\n') {
                    self.index += 1;
                }
                continue;
            }
            if self.peek() == Some(b'\\') && self.bytes.get(self.index + 1) == Some(&b'\n') {
                self.index += 2;
                continue;
            }
            break;
        }
    }

    /// After a value: consume ',' (true = more may follow) or confirm the end / closer.
    fn comma_or_end(&mut self, closer: Option<u8>) -> ParseResult<bool> {
        self.ws();
        match self.peek() {
            Some(b',') => {
                self.index += 1;
                Ok(true)
            }
            None if closer.is_none() => Ok(false),
            Some(byte) if Some(byte) == closer => Ok(false),
            other => Err(format!(
                "unexpected {:?} in macro arguments",
                other.map(char::from)
            )),
        }
    }

    fn ident(&mut self) -> Option<String> {
        let start = self.index;
        if !self.peek().is_some_and(crate::scan::is_ident_start) {
            return None;
        }
        while self.peek().is_some_and(crate::scan::is_ident_continue) {
            self.index += 1;
        }
        Some(self.text[start..self.index].to_owned())
    }

    fn value(&mut self) -> ParseResult<Lit> {
        self.ws();
        let Some(byte) = self.peek() else {
            return Err("missing value".into());
        };
        match byte {
            b'\'' | b'"' => {
                let mut value = self.string(false)?;
                // Implicit concatenation of adjacent literals.
                loop {
                    let save = self.index;
                    self.ws();
                    if matches!(self.peek(), Some(b'\'' | b'"')) {
                        value.push_str(&self.string(false)?);
                    } else {
                        self.index = save;
                        break;
                    }
                }
                Ok(Lit::Str(value))
            }
            b'[' => {
                self.index += 1;
                Ok(Lit::List(self.sequence(b']')?.0))
            }
            b'(' => {
                self.index += 1;
                let (items, trailing_comma) = self.sequence(b')')?;
                if items.len() == 1 && !trailing_comma {
                    Ok(items.into_iter().next().unwrap_or(Lit::None))
                } else {
                    Ok(Lit::Tuple(items))
                }
            }
            b'{' => {
                self.index += 1;
                let mut items = Vec::new();
                loop {
                    self.ws();
                    if self.peek() == Some(b'}') {
                        self.index += 1;
                        break;
                    }
                    let key = self.value()?;
                    self.ws();
                    if self.peek() != Some(b':') {
                        return Err("sets are not supported in macro arguments".into());
                    }
                    self.index += 1;
                    let value = self.value()?;
                    items.push((key, value));
                    if !self.comma_or_end(Some(b'}'))? {
                        self.ws();
                        self.index += 1;
                        break;
                    }
                }
                Ok(Lit::Dict(items))
            }
            b'-' | b'+' => {
                self.index += 1;
                match self.value()? {
                    Lit::Int(value) => Ok(Lit::Int(if byte == b'-' { -value } else { value })),
                    Lit::Float(value) => Ok(Lit::Float(if byte == b'-' {
                        format!("-{value}")
                    } else {
                        value
                    })),
                    _ => Err("unsupported unary value".into()),
                }
            }
            b'0'..=b'9' | b'.' => self.number(),
            _ => {
                let start = self.index;
                let Some(name) = self.ident() else {
                    return Err(format!("unsupported token {:?}", char::from(byte)));
                };
                // String prefixes: r'', b'', u'' (f-strings are not literals).
                if matches!(self.peek(), Some(b'\'' | b'"'))
                    && matches!(name.to_ascii_lowercase().as_str(), "r" | "u")
                {
                    let raw = name.eq_ignore_ascii_case("r");
                    return Ok(Lit::Str(self.string(raw)?));
                }
                match name.as_str() {
                    "True" => Ok(Lit::Bool(true)),
                    "False" => Ok(Lit::Bool(false)),
                    "None" => Ok(Lit::None),
                    _ => {
                        if let Some((_, key)) = self.placeholders.iter().find(|(p, _)| *p == name) {
                            return Ok(Lit::Nested(key.clone()));
                        }
                        self.index = start;
                        Err(format!(
                            "unsupported name or call '{name}' (typed references, expressions)"
                        ))
                    }
                }
            }
        }
    }

    fn sequence(&mut self, closer: u8) -> ParseResult<(Vec<Lit>, bool)> {
        let mut items = Vec::new();
        let mut trailing_comma = false;
        loop {
            self.ws();
            if self.peek() == Some(closer) {
                self.index += 1;
                return Ok((items, trailing_comma));
            }
            items.push(self.value()?);
            trailing_comma = self.comma_or_end(Some(closer))?;
        }
    }

    fn number(&mut self) -> ParseResult<Lit> {
        let start = self.index;
        while self
            .peek()
            .is_some_and(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_'))
            || (matches!(self.peek(), Some(b'+' | b'-'))
                && matches!(self.bytes.get(self.index - 1), Some(b'e' | b'E')))
        {
            self.index += 1;
        }
        let text = self.text[start..self.index].replace('_', "");
        if let Ok(value) = text.parse::<i64>() {
            return Ok(Lit::Int(value));
        }
        if text.parse::<f64>().is_ok() {
            return Ok(Lit::Float(text));
        }
        Err(format!("unsupported number '{text}'"))
    }

    fn string(&mut self, raw: bool) -> ParseResult<String> {
        let quote = self.peek().ok_or("missing quote")?;
        let triple = self.bytes[self.index..].starts_with(&[quote, quote, quote]);
        self.index += if triple { 3 } else { 1 };
        let mut out = String::new();
        loop {
            let Some(byte) = self.peek() else {
                return Err("unterminated string".into());
            };
            if byte == quote {
                if !triple {
                    self.index += 1;
                    return Ok(out);
                }
                if self.bytes[self.index..].starts_with(&[quote, quote, quote]) {
                    self.index += 3;
                    return Ok(out);
                }
            }
            if byte == b'\\' && !raw {
                let next = self
                    .bytes
                    .get(self.index + 1)
                    .copied()
                    .ok_or("bad escape")?;
                self.index += 2;
                match next {
                    b'n' => out.push('\n'),
                    b't' => out.push('\t'),
                    b'r' => out.push('\r'),
                    b'0' => out.push('\0'),
                    b'\\' => out.push('\\'),
                    b'\'' => out.push('\''),
                    b'"' => out.push('"'),
                    b'\n' => {}
                    b'x' | b'u' | b'U' => {
                        let width = match next {
                            b'x' => 2,
                            b'u' => 4,
                            _ => 8,
                        };
                        let hex = self
                            .text
                            .get(self.index..self.index + width)
                            .ok_or("bad escape")?;
                        let code = u32::from_str_radix(hex, 16).map_err(|e| e.to_string())?;
                        out.push(char::from_u32(code).ok_or("bad escape")?);
                        self.index += width;
                    }
                    _ => {
                        out.push('\\');
                        out.push(char::from(next));
                    }
                }
                continue;
            }
            if byte == b'\\' && raw {
                // In raw strings a backslash still prevents the next quote from closing.
                let next = self.bytes.get(self.index + 1).copied();
                out.push('\\');
                self.index += 1;
                if let Some(next) = next
                    && next == quote
                {
                    out.push(char::from(next));
                    self.index += 1;
                }
                continue;
            }
            let ch = self.text[self.index..].chars().next().ok_or("bad utf8")?;
            out.push(ch);
            self.index += ch.len_utf8();
        }
    }
}
