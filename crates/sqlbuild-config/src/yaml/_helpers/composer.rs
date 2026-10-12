//! Compose parser events into one node graph, keeping each node's source marks.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::yaml::_helpers::resolver::resolve_scalar;
use crate::yaml::constants::{MAP_TAG, MAX_NESTING_DEPTH, NON_SPECIFIC_TAG, SEQ_TAG};
use crate::yaml::models::{ComposedDocument, Node, NodeContent};
use saphyr_parser::{Event, Parser, ScalarStyle, ScanError, Span, StrInput, Tag};
use std::borrow::Cow;
use std::collections::{HashMap, HashSet};

type Properties<'input> = (usize, Option<Cow<'input, Tag>>);

/// Composition state of one document.
struct Composer<'input> {
    parser: Parser<'input, StrInput<'input>>,
    chars: Vec<char>,
    document: ComposedDocument,
    anchors: HashMap<usize, usize>,
    open_anchors: HashSet<usize>,
    previous_end: usize,
    current_end: usize,
}

fn syntax_error(error: &ScanError) -> ConfigError {
    ConfigError {
        kind: ConfigErrorKind::Syntax,
        message: error.info().to_owned(),
        line: Some(error.marker().line()),
        column: Some(error.marker().col() + 1),
    }
}

/// The one-based line and column where `span` starts.
fn start_position(span: Span) -> (usize, usize) {
    (span.start.line(), span.start.col() + 1)
}

fn full_tag(tag: Option<&Cow<'_, Tag>>) -> Option<String> {
    tag.map(|tag| format!("{}{}", tag.handle, tag.suffix))
}

fn unsupported(message: &str) -> ConfigError {
    ConfigError::new(ConfigErrorKind::Unsupported, message)
}

impl<'input> Composer<'input> {
    fn next(&mut self) -> Result<(Event<'input>, Span), ConfigError> {
        match self.parser.next_event() {
            Some(Ok(event)) => {
                self.previous_end = self.current_end;
                self.current_end = event.1.end.index();
                Ok(event)
            }
            Some(Err(error)) => Err(syntax_error(&error)),
            None => Err(ConfigError::new(
                ConfigErrorKind::Syntax,
                "unexpected end of stream",
            )),
        }
    }

    fn push(&mut self, tag: String, content: NodeContent, span: Span) -> usize {
        self.document.nodes.push(Node {
            tag,
            content,
            position: start_position(span),
            span: (span.start.index(), span.end.index()),
        });
        self.document.nodes.len() - 1
    }

    fn open_anchor(&mut self, anchor_id: usize) {
        if anchor_id != 0 {
            self.open_anchors.insert(anchor_id);
        }
    }

    fn close_anchor(&mut self, anchor_id: usize, node: usize) -> usize {
        if anchor_id != 0 {
            self.open_anchors.remove(&anchor_id);
            self.anchors.insert(anchor_id, node);
        }
        node
    }

    fn alias(&self, anchor_id: usize) -> Result<usize, ConfigError> {
        if self.open_anchors.contains(&anchor_id) {
            return Err(unsupported("recursive aliases"));
        }
        self.anchors
            .get(&anchor_id)
            .copied()
            .ok_or_else(|| ConfigError::new(ConfigErrorKind::Syntax, "found undefined alias"))
    }

    fn char_at(&self, index: usize) -> Option<char> {
        self.chars.get(index).copied()
    }

    /// The `|` or `>` indicator between the previous event and the block scalar's content.
    fn block_indicator(&self, span: Span) -> Option<usize> {
        let mut index = self.previous_end;
        let mut token_start = true;
        while index <= span.start.index() {
            let character = self.char_at(index)?;
            match character {
                '|' | '>' => return Some(index),
                '#' if token_start => {
                    while !matches!(self.char_at(index), None | Some('\n' | '\r')) {
                        index += 1;
                    }
                    continue;
                }
                '!' | '&' if token_start => {
                    while !matches!(self.char_at(index), None | Some(' ' | '\n' | '\r')) {
                        index += 1;
                    }
                    continue;
                }
                _ => {}
            }
            token_start = matches!(character, ' ' | '\n' | '\r');
            index += 1;
        }
        None
    }

    /// Just past the closing quote of the quoted scalar whose opening quote is at `start`.
    fn quoted_end(&self, start: usize) -> Option<usize> {
        let quote = self.char_at(start)?;
        let mut index = start + 1;
        loop {
            let character = self.char_at(index)?;
            match (quote, character) {
                ('\'', '\'') if self.char_at(index + 1) == Some('\'') => index += 2,
                ('"', '\\') => index += 2,
                (_, character) if character == quote => return Some(index + 1),
                _ => index += 1,
            }
        }
    }

    /// A block scalar's marks: from its indicator to just past the last consumed line break.
    fn block_marks(&self, span: Span) -> (usize, usize) {
        let start = self.block_indicator(span).unwrap_or(span.start.index());
        let end = span.end.index().min(self.chars.len());
        let mut trimmed = end;
        while trimmed > start && self.chars[trimmed - 1] == ' ' {
            trimmed -= 1;
        }
        let after_break = trimmed > start && matches!(self.chars[trimmed - 1], '\n' | '\r');
        (start, if after_break { trimmed } else { end })
    }

    /// The source marks of a scalar, covering its quotes or block indicator.
    fn scalar_marks(&self, style: ScalarStyle, span: Span) -> (usize, usize) {
        match style {
            ScalarStyle::Literal | ScalarStyle::Folded => self.block_marks(span),
            ScalarStyle::SingleQuoted | ScalarStyle::DoubleQuoted => {
                let start = span.start.index();
                (start, self.quoted_end(start).unwrap_or(span.end.index()))
            }
            ScalarStyle::Plain => (span.start.index(), span.end.index()),
        }
    }

    /// A clipped block scalar that runs to the end of input keeps no line break the input lacks.
    fn without_added_final_break<'value>(
        &self,
        value: Cow<'value, str>,
        style: ScalarStyle,
        span: Span,
    ) -> Cow<'value, str> {
        let block = matches!(style, ScalarStyle::Literal | ScalarStyle::Folded);
        let at_end = span.end.index() >= self.chars.len();
        let input_ends_with_break = matches!(self.chars.last(), Some('\n' | '\r'));
        let header: String = self
            .block_indicator(span)
            .map(|indicator| first_word(&self.chars[indicator + 1..]))
            .unwrap_or_default();
        let clipped = !header.contains(['+', '-']);
        if block && at_end && clipped && !input_ends_with_break && value.ends_with('\n') {
            Cow::Owned(value[..value.len() - 1].to_owned())
        } else {
            value
        }
    }

    /// Compose one node; an error without a position is placed at the node's start.
    fn compose_node(
        &mut self,
        event: Event<'input>,
        span: Span,
        depth: usize,
    ) -> Result<usize, ConfigError> {
        let (line, column) = start_position(span);
        self.compose_node_at(event, span, depth)
            .map_err(|error| error.at(line, column))
    }

    fn compose_node_at(
        &mut self,
        event: Event<'input>,
        span: Span,
        depth: usize,
    ) -> Result<usize, ConfigError> {
        if depth > MAX_NESTING_DEPTH {
            return Err(unsupported("nesting deeper than 256 levels"));
        }
        match event {
            Event::Alias(anchor_id) => self.alias(anchor_id),
            Event::Scalar(value, style, anchor_id, tag) => {
                let marks = self.scalar_marks(style, span);
                let value = self.without_added_final_break(value, style, span);
                let tag = scalar_tag(&value, style, full_tag(tag.as_ref()));
                let node = self.push(tag, NodeContent::Scalar(value.into_owned()), span);
                self.document.nodes[node].span = marks;
                Ok(self.close_anchor(anchor_id, node))
            }
            Event::SequenceStart(anchor_id, tag) => {
                self.compose_sequence((anchor_id, tag), span, depth)
            }
            Event::MappingStart(anchor_id, tag) => {
                self.compose_mapping((anchor_id, tag), span, depth)
            }
            _ => Err(ConfigError::new(ConfigErrorKind::Syntax, "expected a node")),
        }
    }

    fn compose_sequence(
        &mut self,
        properties: Properties<'input>,
        span: Span,
        depth: usize,
    ) -> Result<usize, ConfigError> {
        let (anchor_id, tag) = properties;
        self.open_anchor(anchor_id);
        let mut items: Vec<usize> = Vec::new();
        loop {
            let (event, item_span) = self.next()?;
            if matches!(event, Event::SequenceEnd) {
                break;
            }
            items.push(self.compose_node(event, item_span, depth + 1)?);
        }
        let tag = collection_tag(full_tag(tag.as_ref()), SEQ_TAG);
        let node = self.push(tag, NodeContent::Sequence(items), span);
        Ok(self.close_anchor(anchor_id, node))
    }

    fn compose_mapping(
        &mut self,
        properties: Properties<'input>,
        span: Span,
        depth: usize,
    ) -> Result<usize, ConfigError> {
        let (anchor_id, tag) = properties;
        self.open_anchor(anchor_id);
        let mut entries: Vec<(usize, usize)> = Vec::new();
        loop {
            let (event, key_span) = self.next()?;
            if matches!(event, Event::MappingEnd) {
                break;
            }
            let key = self.compose_node(event, key_span, depth + 1)?;
            let (value_event, value_span) = self.next()?;
            let value = self.compose_node(value_event, value_span, depth + 1)?;
            entries.push((key, value));
        }
        let tag = collection_tag(full_tag(tag.as_ref()), MAP_TAG);
        let node = self.push(tag, NodeContent::Mapping(entries), span);
        Ok(self.close_anchor(anchor_id, node))
    }

    /// Compose the only document of the stream; a second document is an error.
    fn compose_stream(mut self) -> Result<ComposedDocument, ConfigError> {
        self.next()?;
        let (event, _) = self.next()?;
        if matches!(event, Event::StreamEnd) {
            return Ok(self.document);
        }
        let (root_event, root_span) = self.next()?;
        let root = self.compose_node(root_event, root_span, 0)?;
        self.document.root = Some(root);
        self.next()?;
        let (after, _) = self.next()?;
        if !matches!(after, Event::StreamEnd) {
            return Err(ConfigError::new(
                ConfigErrorKind::Syntax,
                "expected a single document in the stream",
            ));
        }
        Ok(self.document)
    }
}

/// A scalar's tag: plain scalars and the `!` tag resolve through the core schema.
fn scalar_tag(value: &str, style: ScalarStyle, tag: Option<String>) -> String {
    match tag {
        Some(tag) if tag != NON_SPECIFIC_TAG => tag,
        Some(_) => resolve_scalar(value, false).to_owned(),
        None => resolve_scalar(value, style == ScalarStyle::Plain).to_owned(),
    }
}

fn collection_tag(tag: Option<String>, default: &str) -> String {
    match tag {
        Some(tag) if tag != NON_SPECIFIC_TAG => tag,
        _ => default.to_owned(),
    }
}

/// Compose the single document of `text` into a node graph.
pub(crate) fn compose(text: &str) -> Result<ComposedDocument, ConfigError> {
    Composer {
        parser: Parser::new_from_str(text),
        chars: text.chars().collect(),
        document: ComposedDocument::default(),
        anchors: HashMap::new(),
        open_anchors: HashSet::new(),
        previous_end: 0,
        current_end: 0,
    }
    .compose_stream()
}

/// The characters before the first whitespace.
fn first_word(characters: &[char]) -> String {
    characters
        .iter()
        .take_while(|character| !character.is_whitespace())
        .collect()
}
