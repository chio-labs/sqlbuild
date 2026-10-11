//! Find TOML 1.1 syntax, which the parser accepts and Python's TOML 1.0 `tomllib` rejects.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::toml::_helpers::integers::{Placeholder, large_integer};
use crate::toml::constants::{MAX_CONTAINER_DEPTH, SPLIT_CONTAINER_DEPTH};
use toml_parser::decoder::Encoding;
use toml_parser::parser::{EventReceiver, RecursionGuard, parse_document};
use toml_parser::{ErrorSink, ParseError, Source, Span};

/// Large integers, and the byte ranges of containers nested at the split depth.
pub(crate) type NativeSplits = (Vec<Placeholder>, Vec<(usize, usize)>);

/// The most dotted key segments read natively, which bounds the table nesting of a document.
const MAX_KEY_SEGMENTS: usize = 128;

/// The containers open at the current event.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Container {
    InlineTable,
    Array,
}

/// Records the first TOML 1.1-only construct.
struct VersionReceiver<'text> {
    source: Source<'text>,
    containers: Vec<Container>,
    after_comma: bool,
    key_segments: usize,
    found: Option<(usize, &'static str)>,
    large_integers: Vec<Placeholder>,
    deep_values: Vec<(usize, usize)>,
    deep_start: usize,
}

impl VersionReceiver<'_> {
    fn in_inline_table(&self) -> bool {
        self.containers.last() == Some(&Container::InlineTable)
    }

    fn record(&mut self, span: Span, construct: &'static str) {
        self.found.get_or_insert((span.start(), construct));
    }

    fn token(&mut self) {
        self.after_comma = false;
    }

    fn end_key(&mut self) {
        self.token();
        self.key_segments = 0;
    }

    fn line_break(&mut self, span: Span) {
        if self.in_inline_table() {
            self.record(span, "a newline or comment inside an inline table");
        }
    }

    fn record_large_integer(&mut self, span: Span) {
        let raw = self
            .source
            .get(span)
            .map(|raw| raw.as_str())
            .unwrap_or_default();
        if let Some(digits) = large_integer(raw) {
            self.large_integers
                .push((span.start(), span.end(), ConfigValue::BigInteger(digits)));
        }
    }

    fn open_container(&mut self, span: Span, container: Container) {
        self.containers.push(container);
        if self.containers.len() == SPLIT_CONTAINER_DEPTH {
            self.deep_start = span.start();
        }
    }

    fn close_container(&mut self, span: Span) {
        if self.containers.len() == SPLIT_CONTAINER_DEPTH {
            self.deep_values.push((self.deep_start, span.end()));
        }
        self.containers.pop();
    }

    /// Escapes added by TOML 1.1: `\e` and `\xHH`.
    fn check_escapes(&mut self, span: Span, encoding: Option<Encoding>) {
        if !matches!(
            encoding,
            Some(Encoding::BasicString | Encoding::MlBasicString)
        ) {
            return;
        }
        let raw = self
            .source
            .get(span)
            .map(|raw| raw.as_str())
            .unwrap_or_default();
        let mut escaped = false;
        for character in raw.chars() {
            if escaped && matches!(character, 'e' | 'x') {
                self.record(span, "a \\e or \\x escape");
            }
            escaped = !escaped && character == '\\';
        }
    }
}

impl EventReceiver for VersionReceiver<'_> {
    fn std_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.end_key();
    }

    fn array_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.end_key();
    }

    fn inline_table_open(&mut self, span: Span, _error: &mut dyn ErrorSink) -> bool {
        self.end_key();
        self.open_container(span, Container::InlineTable);
        true
    }

    fn inline_table_close(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        if self.after_comma {
            self.record(span, "a trailing comma in an inline table");
        }
        self.token();
        self.close_container(span);
    }

    fn array_open(&mut self, span: Span, _error: &mut dyn ErrorSink) -> bool {
        self.token();
        self.open_container(span, Container::Array);
        true
    }

    fn array_close(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.token();
        self.close_container(span);
    }

    fn simple_key(&mut self, span: Span, encoding: Option<Encoding>, _error: &mut dyn ErrorSink) {
        self.token();
        self.key_segments += 1;
        if self.key_segments > MAX_KEY_SEGMENTS {
            self.record(span, "a key with more segments than the native limit");
        }
        self.check_escapes(span, encoding);
    }

    fn key_sep(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.token();
    }

    fn key_val_sep(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.end_key();
    }

    fn scalar(&mut self, span: Span, encoding: Option<Encoding>, _error: &mut dyn ErrorSink) {
        self.token();
        self.check_escapes(span, encoding);
        if encoding.is_none() {
            self.record_large_integer(span);
        }
    }

    fn value_sep(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.key_segments = 0;
        self.after_comma = self.in_inline_table();
    }

    fn comment(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.line_break(span);
    }

    fn newline(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.key_segments = 0;
        self.line_break(span);
    }
}

/// Reject TOML 1.1 and syntax errors; return large integers and values nested past the parser.
pub(crate) fn reject_toml_1_1_syntax(text: &str) -> Result<NativeSplits, ConfigError> {
    let source = Source::new(text);
    let tokens = source.lex().into_vec();
    let mut receiver = VersionReceiver {
        source,
        containers: Vec::new(),
        after_comma: false,
        key_segments: 0,
        found: None,
        large_integers: Vec::new(),
        deep_values: Vec::new(),
        deep_start: 0,
    };
    let mut errors: Vec<ParseError> = Vec::new();
    parse_document(
        &tokens,
        &mut RecursionGuard::new(&mut receiver, MAX_CONTAINER_DEPTH),
        &mut errors,
    );
    if let Some(error) = errors.first() {
        let offset = error.unexpected().map_or(0, |span| span.start());
        return Err(ConfigError {
            kind: ConfigErrorKind::Syntax,
            message: error.description().to_owned(),
            line: Some(text.get(..offset).unwrap_or(text).matches('\n').count() + 1),
            column: None,
        });
    }
    match receiver.found {
        None => Ok((receiver.large_integers, receiver.deep_values)),
        Some((offset, construct)) => Err(ConfigError {
            kind: ConfigErrorKind::Syntax,
            message: format!("{construct} is TOML 1.1 syntax, which tomllib rejects"),
            line: Some(text.get(..offset).unwrap_or(text).matches('\n').count() + 1),
            column: None,
        }),
    }
}
