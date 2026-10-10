//! Compose parser events into one node graph, as PyYAML's composer does.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::yaml::_helpers::anchors::{
    anchor_name, code_ends, explicit_key_before, is_python_anchor_name,
};
use crate::yaml::_helpers::block_scalars::{column_of, scan_block_scalar};
use crate::yaml::_helpers::resolver::resolve_scalar;
use crate::yaml::constants::{
    FLOW_KEY_INDICATOR, MAP_TAG, MAX_NATIVE_IMPLICIT_KEY_CHARACTERS, MAX_NESTING_DEPTH,
    NON_SPECIFIC_TAG, PLAIN_FORBIDDEN_FIRST_CHARACTERS, SEQ_TAG, SEQUENCE_ENTRY_TOKEN,
};
use crate::yaml::models::{ComposedDocument, Node, NodeContent};
use saphyr_parser::{Event, Parser, ScalarStyle, ScanError, Span, StrInput, Tag};
use std::borrow::Cow;
use std::collections::{HashMap, HashSet};

type Properties<'input> = (usize, Option<Cow<'input, Tag>>);

/// The block collection a node belongs to, which sets PyYAML's indentation for block scalars.
#[derive(Clone, Copy, Debug)]
enum Parent {
    Document,
    /// A block mapping whose key starts at this char index.
    MappingAt(usize),
    SequenceEntry,
}

/// Where a node sits: its nesting depth, whether a flow collection encloses it, and whether it is a key.
#[derive(Clone, Copy, Debug)]
struct Placement {
    depth: usize,
    flow: bool,
    key: bool,
    parent: Parent,
}

impl Placement {
    fn child(self, flow: bool, key: bool, parent: Parent) -> Self {
        Self {
            depth: self.depth + 1,
            flow: self.flow || flow,
            key,
            parent,
        }
    }
}

/// Composition state of one document.
struct Composer<'input> {
    parser: Parser<'input, StrInput<'input>>,
    chars: Vec<char>,
    code_ends: Vec<usize>,
    document: ComposedDocument,
    anchors: HashMap<usize, usize>,
    anchor_names: HashSet<String>,
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

    fn push(&mut self, tag: String, content: NodeContent, span: Span, decorated: bool) -> usize {
        self.document.nodes.push(Node {
            tag,
            content,
            position: start_position(span),
            span: (span.start.index(), span.end.index()),
            decorated,
        });
        self.document.nodes.len() - 1
    }

    /// Record an anchor before its node's children, rejecting what PyYAML's composer rejects.
    fn open_anchor(&mut self, anchor_id: usize, span: Span) -> Result<(), ConfigError> {
        if anchor_id == 0 {
            return Ok(());
        }
        let name = anchor_name(&self.chars, &self.code_ends, span.start.index())
            .ok_or_else(|| unsupported("this anchor"))?;
        if !is_python_anchor_name(&name) {
            return Err(ConfigError::new(
                ConfigErrorKind::Syntax,
                format!("anchor {name:?} has characters PyYAML does not accept"),
            ));
        }
        if !self.anchor_names.insert(name.clone()) {
            return Err(ConfigError::new(
                ConfigErrorKind::Construct,
                format!("found duplicate anchor {name:?}"),
            ));
        }
        self.open_anchors.insert(anchor_id);
        Ok(())
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

    /// An implicit key's extent from its first property to its `:` indicator; `None` if explicit.
    fn implicit_key_extent(&self, span: Span) -> Option<(usize, usize)> {
        let key_end = span.end.index().min(self.chars.len());
        let indicator = (key_end..self.chars.len())
            .find(|index| !matches!(self.chars[*index], ' ' | '\t' | '\n' | '\r'))
            .filter(|index| self.chars[*index] == ':');
        let end = indicator.unwrap_or(key_end);
        let mut start = self.previous_end;
        while start < end {
            match self.chars[start] {
                ' ' | '\t' | '\n' | '\r' | ',' | '[' | '{' => start += 1,
                '#' => {
                    while start < end && !matches!(self.chars[start], '\n' | '\r') {
                        start += 1;
                    }
                }
                _ => break,
            }
        }
        let explicit = self.chars.get(start) == Some(&'?')
            && matches!(
                self.char_at(start + 1),
                None | Some(' ' | '\t' | '\n' | '\r')
            );
        (!explicit).then_some((start.min(end), end))
    }

    /// Whether an implicit key, from its first property to its `:` indicator, covers a line break.
    fn spans_lines(&self, span: Span) -> bool {
        self.implicit_key_extent(span).is_some_and(|(start, end)| {
            self.chars[start..end]
                .iter()
                .any(|character| matches!(character, '\n' | '\r'))
        })
    }

    /// Whether an implicit key nears PyYAML's 1024-character simple-key limit.
    fn is_long_implicit_key(&self, span: Span) -> bool {
        self.implicit_key_extent(span)
            .is_some_and(|(start, end)| end - start > MAX_NATIVE_IMPLICIT_KEY_CHARACTERS)
    }

    /// Whether the collection starting at `span` is written in flow style.
    fn is_flow(&self, span: Span) -> bool {
        span.end.index() > span.start.index()
            && matches!(self.char_at(span.start.index()), Some('[' | '{'))
    }

    /// Reject plain scalars PyYAML's scanner reads differently from YAML 1.2.
    fn check_plain(
        &self,
        value: &str,
        span: Span,
        placement: Placement,
    ) -> Result<(), ConfigError> {
        let start = span.start.index();
        let first = self.char_at(start);
        if placement.flow && first == Some(':') && !value.is_empty() {
            return Err(ConfigError::new(
                ConfigErrorKind::Syntax,
                "a plain scalar in a flow collection cannot start with ':'",
            ));
        }
        let colon = (span.end.index()..self.chars.len())
            .find(|index| !matches!(self.chars[*index], ' ' | '\t'))
            .unwrap_or(self.chars.len());
        let adjacent_value = self.char_at(colon) == Some(':')
            && matches!(self.char_at(colon + 1), Some(',' | ']' | '}'));
        if placement.flow && adjacent_value {
            return Err(unsupported(
                "':' directly before ',', ']' or '}' in a flow collection",
            ));
        }
        let explicit_key = explicit_key_before(&self.chars, &self.code_ends, start);
        if placement.key && value.is_empty() && first == Some(':') && !explicit_key {
            return Err(ConfigError::new(
                ConfigErrorKind::Syntax,
                "a mapping key cannot be empty without '?'",
            ));
        }
        Ok(())
    }

    /// The block scalar indicator between the previous event and the scalar's content.
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

    /// PyYAML's block scalar marks: indicator to just past the last consumed line break.
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

    /// The column of the `-` that starts the sequence entry holding the indicator at `indicator`.
    fn entry_column(&self, indicator: usize) -> Option<usize> {
        let mut end = indicator;
        loop {
            while end > 0 && self.chars[end - 1] == ' ' {
                end -= 1;
            }
            let start = self.chars[..end]
                .iter()
                .rposition(|character| matches!(character, ' ' | '\n' | '\r'))
                .map_or(0, |boundary| boundary + 1);
            let token: String = self.chars[start..end].iter().collect();
            if token.starts_with(['!', '&']) {
                end = start;
                continue;
            }
            return (token == SEQUENCE_ENTRY_TOKEN && end < indicator)
                .then(|| column_of(&self.chars, start));
        }
    }

    /// PyYAML's value for a literal or folded scalar, cross-checked against the parser's reading.
    fn block_scalar(
        &self,
        parsed: &str,
        span: Span,
        placement: Placement,
    ) -> Result<String, ConfigError> {
        let deferred = || unsupported("this literal or folded block scalar layout");
        if placement.flow || placement.key {
            return Err(deferred());
        }
        let indicator = self.block_indicator(span).ok_or_else(deferred)?;
        let parent_indent = match placement.parent {
            Parent::Document => None,
            Parent::MappingAt(key_start) => Some(column_of(&self.chars, key_start)),
            Parent::SequenceEntry => Some(self.entry_column(indicator).ok_or_else(deferred)?),
        };
        let (value, end) =
            scan_block_scalar(&self.chars, indicator, parent_indent).ok_or_else(deferred)?;
        let parsed_end = span.end.index();
        let gap = &self.chars[end.min(parsed_end)..end.max(parsed_end).min(self.chars.len())];
        let same_end = gap
            .iter()
            .all(|character| matches!(character, ' ' | '\n' | '\r'));
        let same_content = value.trim_end_matches('\n') == parsed.trim_end_matches('\n');
        (same_end && same_content)
            .then_some(value)
            .ok_or_else(deferred)
    }

    /// Compose one node; an error without a position is placed at the node's start.
    fn compose_node(
        &mut self,
        event: Event<'input>,
        span: Span,
        placement: Placement,
    ) -> Result<usize, ConfigError> {
        let (line, column) = start_position(span);
        self.compose_node_at(event, span, placement)
            .map_err(|error| error.at(line, column))
    }

    fn compose_node_at(
        &mut self,
        event: Event<'input>,
        span: Span,
        placement: Placement,
    ) -> Result<usize, ConfigError> {
        if placement.depth > MAX_NESTING_DEPTH {
            return Err(unsupported("nesting deeper than 256 levels"));
        }
        match event {
            Event::Alias(anchor_id) => self.alias(anchor_id),
            Event::Scalar(value, style, anchor_id, tag) => {
                if style == ScalarStyle::Plain
                    && placement.flow
                    && value.contains(FLOW_KEY_INDICATOR)
                {
                    return Err(unsupported(
                        "'?' inside a plain scalar in a flow collection",
                    ));
                }
                if style == ScalarStyle::Plain
                    && value.starts_with(PLAIN_FORBIDDEN_FIRST_CHARACTERS)
                {
                    return Err(ConfigError::new(
                        ConfigErrorKind::Syntax,
                        "a plain scalar cannot start with this indicator",
                    ));
                }
                let flow_value_indicator = placement.flow && value.starts_with(':');
                if style == ScalarStyle::Plain && flow_value_indicator {
                    return Err(ConfigError::new(
                        ConfigErrorKind::Syntax,
                        "a plain scalar in a flow collection cannot start with ':'",
                    ));
                }
                if placement.key && self.is_long_implicit_key(span) {
                    return Err(unsupported("implicit keys longer than 1000 characters"));
                }
                if placement.key && placement.flow && self.spans_lines(span) {
                    return Err(ConfigError::new(
                        ConfigErrorKind::Syntax,
                        "an implicit key in a flow collection must fit on one line",
                    ));
                }
                if style == ScalarStyle::Plain && tag.is_none() && anchor_id == 0 {
                    self.check_plain(&value, span, placement)?;
                }
                let (value, marks) = match style {
                    ScalarStyle::Literal | ScalarStyle::Folded => (
                        Cow::Owned(self.block_scalar(&value, span, placement)?),
                        self.block_marks(span),
                    ),
                    _ => (value, (span.start.index(), span.end.index())),
                };
                let non_specific = full_tag(tag.as_ref()).as_deref() == Some(NON_SPECIFIC_TAG);
                if non_specific && value.is_empty() && style == ScalarStyle::Plain {
                    return Err(unsupported("an empty scalar tagged '!'"));
                }
                self.open_anchor(anchor_id, span)?;
                let decorated = anchor_id != 0 || tag.is_some();
                let tag = scalar_tag(&value, style, full_tag(tag.as_ref()));
                let node = self.push(
                    tag,
                    NodeContent::Scalar(value.into_owned()),
                    span,
                    decorated,
                );
                self.document.nodes[node].span = marks;
                Ok(self.close_anchor(anchor_id, node))
            }
            Event::SequenceStart(anchor_id, tag) => {
                self.compose_sequence((anchor_id, tag), span, placement)
            }
            Event::MappingStart(anchor_id, tag) => {
                self.compose_mapping((anchor_id, tag), span, placement)
            }
            _ => Err(ConfigError::new(ConfigErrorKind::Syntax, "expected a node")),
        }
    }

    fn compose_sequence(
        &mut self,
        properties: Properties<'input>,
        span: Span,
        placement: Placement,
    ) -> Result<usize, ConfigError> {
        let (anchor_id, tag) = properties;
        self.open_anchor(anchor_id, span)?;
        let item_placement = placement.child(self.is_flow(span), false, Parent::SequenceEntry);
        let mut items: Vec<usize> = Vec::new();
        loop {
            let (event, item_span) = self.next()?;
            if matches!(event, Event::SequenceEnd) {
                break;
            }
            items.push(self.compose_node(event, item_span, item_placement)?);
        }
        let decorated = anchor_id != 0 || tag.is_some();
        let tag = collection_tag(full_tag(tag.as_ref()), SEQ_TAG);
        let node = self.push(tag, NodeContent::Sequence(items), span, decorated);
        Ok(self.close_anchor(anchor_id, node))
    }

    fn compose_mapping(
        &mut self,
        properties: Properties<'input>,
        span: Span,
        placement: Placement,
    ) -> Result<usize, ConfigError> {
        let (anchor_id, tag) = properties;
        self.open_anchor(anchor_id, span)?;
        let flow = self.is_flow(span);
        let mut entries: Vec<(usize, usize)> = Vec::new();
        loop {
            let (event, key_span) = self.next()?;
            if matches!(event, Event::MappingEnd) {
                break;
            }
            let key_parent = Parent::MappingAt(key_span.start.index());
            let key =
                self.compose_node(event, key_span, placement.child(flow, true, key_parent))?;
            let (value_event, value_span) = self.next()?;
            let value_placement = placement.child(flow, false, key_parent);
            let value = self.compose_node(value_event, value_span, value_placement)?;
            entries.push((key, value));
        }
        let decorated = anchor_id != 0 || tag.is_some();
        let tag = collection_tag(full_tag(tag.as_ref()), MAP_TAG);
        let node = self.push(tag, NodeContent::Mapping(entries), span, decorated);
        Ok(self.close_anchor(anchor_id, node))
    }

    /// Compose the only document of the stream; a second document is an error, as in PyYAML.
    fn compose_stream(mut self) -> Result<ComposedDocument, ConfigError> {
        self.next()?;
        let (event, _) = self.next()?;
        if matches!(event, Event::StreamEnd) {
            return Ok(self.document);
        }
        let (root_event, root_span) = self.next()?;
        let root_placement = Placement {
            depth: 0,
            flow: false,
            key: false,
            parent: Parent::Document,
        };
        let root = self.compose_node(root_event, root_span, root_placement)?;
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

/// PyYAML's tag for a scalar: plain scalars and the `!` tag resolve implicitly.
fn scalar_tag(value: &str, style: ScalarStyle, tag: Option<String>) -> String {
    match tag {
        Some(tag) if tag != NON_SPECIFIC_TAG => tag,
        Some(_) => resolve_scalar(value, true).to_owned(),
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
    let chars: Vec<char> = text.chars().collect();
    Composer {
        parser: Parser::new_from_str(text),
        code_ends: code_ends(&chars),
        chars,
        document: ComposedDocument::default(),
        anchors: HashMap::new(),
        anchor_names: HashSet::new(),
        open_anchors: HashSet::new(),
        previous_end: 0,
        current_end: 0,
    }
    .compose_stream()
}
