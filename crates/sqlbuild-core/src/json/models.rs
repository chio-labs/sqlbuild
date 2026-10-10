//! JSON values and the Python serializer configurations the emitter reproduces.

/// A JSON value with Python's value domain; objects keep insertion order and unique keys.
#[derive(Clone, Debug, PartialEq)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Integer(JsonInteger),
    Float(f64),
    String(String),
    /// A Python `str` as UTF-16 code units, for text holding lone surrogates.
    Utf16(Vec<u16>),
    Array(Vec<JsonValue>),
    Object(Vec<(String, JsonValue)>),
}

/// An arbitrary-precision integer as canonical decimal text without leading zeros or `-0`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct JsonInteger {
    decimal: String,
}

/// Which Python serializer, with which options, to reproduce.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum JsonDialect {
    /// The standard library's `json.dumps`.
    Stdlib(StdlibJsonOptions),
    /// `orjson.dumps`.
    Orjson(OrjsonOptions),
}

/// Options of `json.dumps`, with the same meaning and defaults.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StdlibJsonOptions {
    /// `indent`, as the string repeated once per nesting level (`indent=2` is two spaces).
    pub indent: Option<String>,
    /// First element of `separators`.
    pub item_separator: String,
    /// Second element of `separators`.
    pub key_separator: String,
    pub ensure_ascii: bool,
    pub sort_keys: bool,
    pub allow_nan: bool,
}

/// The `orjson` options SQLBuild uses; every other option is off.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct OrjsonOptions {
    /// `orjson.OPT_INDENT_2`.
    pub indent_2: bool,
    /// `orjson.OPT_SORT_KEYS`.
    pub sort_keys: bool,
}

impl StdlibJsonOptions {
    /// The options of `json.dumps(value, indent=indent)`, with Python's default separators.
    pub fn new(indent: Option<usize>) -> Self {
        let item_separator = if indent.is_some() { "," } else { ", " };
        Self {
            indent: indent.map(|width| " ".repeat(width)),
            item_separator: item_separator.to_owned(),
            key_separator: ": ".to_owned(),
            ensure_ascii: true,
            sort_keys: false,
            allow_nan: true,
        }
    }

    /// The same options with `separators=(item_separator, key_separator)`.
    pub fn with_separators(self, item_separator: &str, key_separator: &str) -> Self {
        Self {
            item_separator: item_separator.to_owned(),
            key_separator: key_separator.to_owned(),
            ..self
        }
    }
}

impl JsonInteger {
    /// Parse decimal text with an optional sign and leading zeros, as Python's `int()` does.
    pub fn parse(text: &str) -> Option<Self> {
        let (negative, digits) = match text.as_bytes().first()? {
            b'-' => (true, &text[1..]),
            b'+' => (false, &text[1..]),
            _ => (false, text),
        };
        if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        let significant = digits.trim_start_matches('0');
        let decimal = match (significant.is_empty(), negative) {
            (true, _) => "0".to_owned(),
            (false, true) => format!("-{significant}"),
            (false, false) => significant.to_owned(),
        };
        Some(Self { decimal })
    }

    /// The canonical decimal text.
    pub fn as_str(&self) -> &str {
        &self.decimal
    }

    /// The value as an `i128`, or `None` when it needs more than 128 bits.
    pub fn to_i128(&self) -> Option<i128> {
        let (sign, digits) = match self.decimal.strip_prefix('-') {
            Some(digits) => (-1, digits),
            None => (1, self.decimal.as_str()),
        };
        digits.bytes().try_fold(0_i128, |total, digit| {
            total
                .checked_mul(10)?
                .checked_add(sign * i128::from(digit - b'0'))
        })
    }
}

impl From<i64> for JsonInteger {
    fn from(value: i64) -> Self {
        Self {
            decimal: value.to_string(),
        }
    }
}

impl From<u64> for JsonInteger {
    fn from(value: u64) -> Self {
        Self {
            decimal: value.to_string(),
        }
    }
}

impl From<i128> for JsonInteger {
    fn from(value: i128) -> Self {
        Self {
            decimal: value.to_string(),
        }
    }
}
