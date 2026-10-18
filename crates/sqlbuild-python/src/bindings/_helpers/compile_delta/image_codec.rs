//! The project image's binary sections: the native store's length-prefixed records, with each
//! distinct string written once and referred to by its index.

use std::collections::HashMap;

use sqlbuild_cache::store::models::{RecordReader, RecordWriter};

/// The most items a list reserves room for before reading them, against corrupt counts.
const MAX_RESERVED_ITEMS: usize = 1 << 16;

/// Writes one section: its values refer to a table of the distinct strings they hold.
#[derive(Default)]
pub(crate) struct Encoder<'a> {
    ids: HashMap<&'a str, u64>,
    strings: Vec<&'a str>,
    body: RecordWriter,
}

impl<'a> Encoder<'a> {
    pub(crate) fn string(&mut self, value: &'a str) {
        let next: u64 = self.strings.len() as u64;
        let id: u64 = *self.ids.entry(value).or_insert(next);
        if id == next {
            self.strings.push(value);
        }
        self.body.put_u64(id);
    }

    pub(crate) fn optional_string(&mut self, value: Option<&'a str>) {
        self.flag(value.is_some());
        if let Some(value) = value {
            self.string(value);
        }
    }

    pub(crate) fn count(&mut self, count: usize) {
        self.body.put_u64(count as u64);
    }

    pub(crate) fn flag(&mut self, value: bool) {
        self.body.put_u64(u64::from(value));
    }

    pub(crate) fn bytes(&mut self, value: &[u8]) {
        self.body.put_bytes(value);
    }

    pub(crate) fn strings(&mut self, values: impl ExactSizeIterator<Item = &'a str>) {
        self.count(values.len());
        for value in values {
            self.string(value);
        }
    }

    pub(crate) fn pairs(&mut self, pairs: &'a [(String, String)]) {
        self.count(pairs.len());
        for (left, right) in pairs {
            self.string(left);
            self.string(right);
        }
    }

    /// The section: the string table, then the values.
    pub(crate) fn finish(self) -> Vec<u8> {
        let mut section: RecordWriter = RecordWriter::default();
        section.put_u64(self.strings.len() as u64);
        for value in &self.strings {
            section.put_str(value);
        }
        section.put_bytes(&self.body.into_bytes());
        section.into_bytes()
    }
}

/// Reads a section an [`Encoder`] wrote; any malformed value fails the whole read.
pub(crate) struct Decoder<'a> {
    strings: Vec<String>,
    body: RecordReader<'a>,
}

impl<'a> Decoder<'a> {
    pub(crate) fn new(section: &'a [u8]) -> Option<Self> {
        let mut reader: RecordReader<'a> = RecordReader::new(section);
        let count: usize = usize::try_from(reader.u64().ok()?).ok()?;
        let mut strings: Vec<String> = Vec::with_capacity(count.min(section.len()));
        for _ in 0..count {
            strings.push(reader.string().ok()?);
        }
        let body: &'a [u8] = reader.bytes().ok()?;
        reader.finish().ok()?;
        Some(Self {
            strings,
            body: RecordReader::new(body),
        })
    }

    pub(crate) fn string(&mut self) -> Option<String> {
        let id: usize = usize::try_from(self.body.u64().ok()?).ok()?;
        self.strings.get(id).cloned()
    }

    pub(crate) fn optional_string(&mut self) -> Option<Option<String>> {
        Some(if self.flag()? {
            Some(self.string()?)
        } else {
            None
        })
    }

    pub(crate) fn count(&mut self) -> Option<usize> {
        usize::try_from(self.body.u64().ok()?).ok()
    }

    pub(crate) fn flag(&mut self) -> Option<bool> {
        match self.body.u64().ok()? {
            0 => Some(false),
            1 => Some(true),
            _ => None,
        }
    }

    pub(crate) fn bytes(&mut self) -> Option<&'a [u8]> {
        self.body.bytes().ok()
    }

    pub(crate) fn list<T>(
        &mut self,
        mut item: impl FnMut(&mut Self) -> Option<T>,
    ) -> Option<Vec<T>> {
        let count: usize = self.count()?;
        let mut items: Vec<T> = Vec::with_capacity(count.min(MAX_RESERVED_ITEMS));
        for _ in 0..count {
            items.push(item(self)?);
        }
        Some(items)
    }

    pub(crate) fn strings(&mut self) -> Option<Vec<String>> {
        self.list(Self::string)
    }

    pub(crate) fn pairs(&mut self) -> Option<Vec<(String, String)>> {
        self.list(|decoder| Some((decoder.string()?, decoder.string()?)))
    }

    /// Whether every value was read.
    pub(crate) fn finish(self) -> Option<()> {
        self.body.finish().ok()
    }
}
