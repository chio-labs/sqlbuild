//! `tomllib`'s namespace rules: which tables, dotted keys and arrays of tables may be (re)opened.

use crate::errors::{ConfigError, ConfigErrorKind};
use std::collections::HashMap;
use toml_parser::decoder::Encoding;
use toml_parser::parser::{EventReceiver, RecursionGuard, parse_document};
use toml_parser::{ErrorSink, ParseError, Raw, Source, Span};

/// `Flags.FROZEN`: a value written with `=`, which later statements cannot extend.
const FROZEN: u8 = 1;
/// `Flags.EXPLICIT_NEST`: a table declared by a header or opened by a dotted key.
const EXPLICIT_NEST: u8 = 2;
/// The container depth the version check already enforces.
const MAX_CONTAINER_DEPTH: u32 = 80;

/// One key of `tomllib`'s `Flags` tree.
#[derive(Default)]
struct FlagNode {
    flags: u8,
    recursive: u8,
    nested: HashMap<String, FlagNode>,
}

/// `tomllib`'s `Flags`, keyed by table names without array indices.
#[derive(Default)]
struct Flags {
    root: HashMap<String, FlagNode>,
    pending: Vec<Vec<String>>,
}

impl Flags {
    fn is(&self, key: &[String], flag: u8) -> bool {
        let Some((stem, parent)) = key.split_last() else {
            return false;
        };
        let mut container = &self.root;
        for name in parent {
            let Some(inner) = container.get(name) else {
                return false;
            };
            if inner.recursive & flag != 0 {
                return true;
            }
            container = &inner.nested;
        }
        container
            .get(stem)
            .is_some_and(|node| (node.flags | node.recursive) & flag != 0)
    }

    fn set(&mut self, key: &[String], flag: u8, recursive: bool) {
        let Some((stem, parent)) = key.split_last() else {
            return;
        };
        let mut container = &mut self.root;
        for name in parent {
            container = &mut container.entry(name.clone()).or_default().nested;
        }
        let node = container.entry(stem.clone()).or_default();
        match recursive {
            true => node.recursive |= flag,
            false => node.flags |= flag,
        }
    }

    fn unset_all(&mut self, key: &[String]) {
        let Some((stem, parent)) = key.split_last() else {
            return;
        };
        let mut container = &mut self.root;
        for name in parent {
            let Some(inner) = container.get_mut(name) else {
                return;
            };
            container = &mut inner.nested;
        }
        container.remove(stem);
    }

    fn finalize_pending(&mut self) {
        for key in std::mem::take(&mut self.pending) {
            self.set(&key, EXPLICIT_NEST, false);
        }
    }
}

/// What `tomllib`'s `NestedDict` holds behind one key.
enum Entry {
    Table(HashMap<String, Entry>),
    Tables(Vec<HashMap<String, Entry>>),
    Value,
}

/// `tomllib`'s `NestedDict`: the tables and values created so far.
#[derive(Default)]
struct NestedDict {
    root: HashMap<String, Entry>,
}

impl NestedDict {
    /// `get_or_create_nest`; `None` where `tomllib` raises "There is no nest behind this key".
    fn nest(&mut self, key: &[String], access_lists: bool) -> Option<&mut HashMap<String, Entry>> {
        let mut container = &mut self.root;
        for name in key {
            let entry = container
                .entry(name.clone())
                .or_insert_with(|| Entry::Table(HashMap::new()));
            container = match entry {
                Entry::Table(table) => table,
                Entry::Tables(tables) if access_lists => tables.last_mut()?,
                _ => return None,
            };
        }
        Some(container)
    }
}

/// The keys and values of one inline table, checked as `tomllib`'s `parse_inline_table` does.
#[derive(Default)]
struct InlineTable {
    data: NestedDict,
    flags: Flags,
    key: Vec<String>,
}

impl InlineTable {
    fn insert(&mut self, container_value: bool) -> bool {
        let key = std::mem::take(&mut self.key);
        let Some((stem, parent)) = key.split_last() else {
            return false;
        };
        if self.flags.is(&key, FROZEN) {
            return false;
        }
        let Some(table) = self.data.nest(parent, false) else {
            return false;
        };
        if table.contains_key(stem) {
            return false;
        }
        table.insert(stem.clone(), Entry::Value);
        if container_value {
            self.flags.set(&key, FROZEN, true);
        }
        true
    }
}

/// An open array or inline table inside a value.
enum Frame {
    Array,
    InlineTable(InlineTable),
}

/// Replays `tomllib.loads`' bookkeeping over parser events and records the first rejection.
struct NamespaceReceiver<'text> {
    source: Source<'text>,
    data: NestedDict,
    flags: Flags,
    header: Vec<String>,
    key: Vec<String>,
    frames: Vec<Frame>,
    rejected: Option<(usize, &'static str)>,
}

impl NamespaceReceiver<'_> {
    fn reject(&mut self, span: Span, reason: &'static str) {
        self.rejected.get_or_insert((span.start(), reason));
    }

    fn decode(&self, span: Span, encoding: Option<Encoding>) -> String {
        let raw = self.source.get(span).map_or("", |raw| raw.as_str());
        let mut decoded = String::new();
        let mut ignored: Vec<ParseError> = Vec::new();
        Raw::new_unchecked(raw, encoding, span).decode_key(&mut decoded, &mut ignored);
        decoded
    }

    /// `key_value_rule` for a key-value pair under the current header.
    fn key_value(&mut self, span: Span, container_value: bool) {
        let key = std::mem::take(&mut self.key);
        let Some((stem, parent)) = key.split_last() else {
            return;
        };
        for length in 1..key.len() {
            let container: Vec<String> = [&self.header[..], &key[..length]].concat();
            if self.flags.is(&container, EXPLICIT_NEST) {
                return self.reject(span, "Cannot redefine namespace");
            }
            self.flags.pending.push(container);
        }
        let parent_key: Vec<String> = [&self.header[..], parent].concat();
        if self.flags.is(&parent_key, FROZEN) {
            return self.reject(span, "Cannot mutate immutable namespace");
        }
        let Some(table) = self.data.nest(&parent_key, true) else {
            return self.reject(span, "Cannot overwrite a value");
        };
        if table.contains_key(stem) {
            return self.reject(span, "Cannot overwrite a value");
        }
        table.insert(stem.clone(), Entry::Value);
        if container_value {
            let full_key: Vec<String> = [&self.header[..], &key[..]].concat();
            self.flags.set(&full_key, FROZEN, true);
        }
    }

    /// `create_dict_rule` for a `[table]` header.
    fn table(&mut self, span: Span) {
        let key = std::mem::take(&mut self.key);
        if self.flags.is(&key, EXPLICIT_NEST) || self.flags.is(&key, FROZEN) {
            return self.reject(span, "Cannot declare a table twice");
        }
        self.flags.set(&key, EXPLICIT_NEST, false);
        if self.data.nest(&key, true).is_none() {
            return self.reject(span, "Cannot overwrite a value");
        }
        self.header = key;
    }

    /// `create_list_rule` for an `[[array of tables]]` header.
    fn array_of_tables(&mut self, span: Span) {
        let key = std::mem::take(&mut self.key);
        let Some((stem, parent)) = key.split_last() else {
            return;
        };
        if self.flags.is(&key, FROZEN) {
            return self.reject(span, "Cannot mutate immutable namespace");
        }
        self.flags.unset_all(&key);
        self.flags.set(&key, EXPLICIT_NEST, false);
        let Some(table) = self.data.nest(parent, true) else {
            return self.reject(span, "Cannot overwrite a value");
        };
        match table.get_mut(stem) {
            None => {
                table.insert(stem.clone(), Entry::Tables(vec![HashMap::new()]));
            }
            Some(Entry::Tables(tables)) => tables.push(HashMap::new()),
            Some(_) => return self.reject(span, "Cannot overwrite a value"),
        }
        self.header = key;
    }

    /// A complete value: a scalar, or an array or inline table that just closed.
    fn value(&mut self, span: Span, container_value: bool) {
        match self.frames.last_mut() {
            None => self.key_value(span, container_value),
            Some(Frame::Array) => {}
            Some(Frame::InlineTable(table)) => {
                if !table.insert(container_value) {
                    self.reject(span, "Cannot redefine an inline table key");
                }
            }
        }
    }

    fn open_header(&mut self) {
        self.flags.finalize_pending();
        self.key.clear();
    }
}

impl EventReceiver for NamespaceReceiver<'_> {
    fn std_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.open_header();
    }

    fn std_table_close(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.table(span);
    }

    fn array_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.open_header();
    }

    fn array_table_close(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.array_of_tables(span);
    }

    fn inline_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) -> bool {
        self.frames.push(Frame::InlineTable(InlineTable::default()));
        true
    }

    fn inline_table_close(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.frames.pop();
        self.value(span, true);
    }

    fn array_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) -> bool {
        self.frames.push(Frame::Array);
        true
    }

    fn array_close(&mut self, span: Span, _error: &mut dyn ErrorSink) {
        self.frames.pop();
        self.value(span, true);
    }

    fn simple_key(&mut self, span: Span, encoding: Option<Encoding>, _error: &mut dyn ErrorSink) {
        let segment = self.decode(span, encoding);
        match self.frames.last_mut() {
            Some(Frame::InlineTable(table)) => table.key.push(segment),
            Some(Frame::Array) => {}
            None => self.key.push(segment),
        }
    }

    fn scalar(&mut self, span: Span, _encoding: Option<Encoding>, _error: &mut dyn ErrorSink) {
        self.value(span, false);
    }
}

/// Reject what `tomllib` rejects as a redefined or immutable namespace.
pub(crate) fn reject_namespace_conflicts(text: &str) -> Result<(), ConfigError> {
    let source = Source::new(text);
    let tokens = source.lex().into_vec();
    let mut receiver = NamespaceReceiver {
        source,
        data: NestedDict::default(),
        flags: Flags::default(),
        header: Vec::new(),
        key: Vec::new(),
        frames: Vec::new(),
        rejected: None,
    };
    let mut errors: Vec<ParseError> = Vec::new();
    parse_document(
        &tokens,
        &mut RecursionGuard::new(&mut receiver, MAX_CONTAINER_DEPTH),
        &mut errors,
    );
    match receiver.rejected {
        None => Ok(()),
        Some((offset, reason)) => Err(ConfigError {
            kind: ConfigErrorKind::Syntax,
            message: reason.to_owned(),
            line: Some(text.get(..offset).unwrap_or(text).matches('\n').count() + 1),
            column: None,
        }),
    }
}
