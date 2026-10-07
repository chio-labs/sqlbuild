//! Anchored, hand-written equivalents of PyYAML's regular expressions.

/// A cursor over ASCII bytes for hand-written, anchored versions of PyYAML's patterns.
#[derive(Clone, Debug)]
pub(crate) struct PatternCursor<'text> {
    bytes: &'text [u8],
    position: usize,
}

impl<'text> PatternCursor<'text> {
    pub(crate) fn new(text: &'text str) -> Self {
        Self {
            bytes: text.as_bytes(),
            position: 0,
        }
    }

    /// Whether one alternative consumes all of `text`, like an anchored regular expression.
    pub(crate) fn matches_any(
        text: &str,
        alternatives: &[fn(&mut PatternCursor<'_>) -> bool],
    ) -> bool {
        alternatives.iter().any(|alternative| {
            let mut cursor = PatternCursor::new(text);
            alternative(&mut cursor) && cursor.at_end()
        })
    }

    pub(crate) fn peek(&self) -> Option<u8> {
        self.bytes.get(self.position).copied()
    }

    pub(crate) fn position(&self) -> usize {
        self.position
    }

    pub(crate) fn rewind(&mut self, position: usize) {
        self.position = position;
    }

    /// Exactly one byte accepted by `accept`.
    pub(crate) fn one(&mut self, accept: impl Fn(u8) -> bool) -> bool {
        let matched = self.peek().is_some_and(accept);
        self.position += usize::from(matched);
        matched
    }

    /// Zero or more bytes accepted by `accept`; always succeeds.
    pub(crate) fn many(&mut self, accept: impl Fn(u8) -> bool) -> bool {
        while self.one(&accept) {}
        true
    }

    /// One or more bytes accepted by `accept`.
    pub(crate) fn some(&mut self, accept: impl Fn(u8) -> bool) -> bool {
        self.one(&accept) && self.many(accept)
    }

    /// Up to `limit` bytes accepted by `accept`, returning how many were taken.
    pub(crate) fn up_to(&mut self, limit: usize, accept: impl Fn(u8) -> bool) -> usize {
        let start = self.position;
        while self.position - start < limit && self.one(&accept) {}
        self.position - start
    }

    pub(crate) fn literal(&mut self, text: &str) -> bool {
        let matched = self.bytes[self.position..].starts_with(text.as_bytes());
        self.position += usize::from(matched) * text.len();
        matched
    }

    pub(crate) fn any_literal(&mut self, texts: &[&str]) -> bool {
        texts.iter().any(|text| self.literal(text))
    }

    /// An optional `-` or `+`; always succeeds.
    pub(crate) fn sign(&mut self) -> bool {
        self.one(|byte| byte == b'-' || byte == b'+');
        true
    }

    /// The optional exponent `[eE][-+][0-9]+`; always succeeds.
    pub(crate) fn exponent(&mut self) -> bool {
        let start = self.position;
        let complete = self.one(|byte| byte == b'e' || byte == b'E')
            && self.one(|byte| byte == b'-' || byte == b'+')
            && self.some(|byte| byte.is_ascii_digit());
        if !complete {
            self.position = start;
        }
        true
    }

    /// `(?::[0-5]?[0-9])+`, one or more sexagesimal groups.
    pub(crate) fn sexagesimal_groups(&mut self) -> bool {
        let mut groups = 0;
        while self.peek() == Some(b':') {
            let width = match &self.bytes[self.position + 1..] {
                [b'0'..=b'5', b'0'..=b'9', ..] => 2,
                [b'0'..=b'9', ..] => 1,
                _ => return false,
            };
            self.position += 1 + width;
            groups += 1;
        }
        groups > 0
    }

    pub(crate) fn at_end(&self) -> bool {
        self.position == self.bytes.len()
    }
}
