//! The shared native store: one file per cache kind, keyed by content digests.

use std::collections::HashMap;
use std::io::Write;
use std::path::Path;

use crate::digest::types::ContentDigest;
use crate::store::_helpers::frame::{StoreFile, encode_store};
use crate::store::constants::RETAINED_GENERATIONS;
use crate::store::errors::StoreDecodeError;

/// Length-prefixed fields of one stored value.
#[derive(Debug, Default)]
pub struct RecordWriter {
    bytes: Vec<u8>,
}

impl RecordWriter {
    pub fn put_u64(&mut self, value: u64) {
        self.bytes.extend_from_slice(&value.to_le_bytes());
    }

    pub fn put_bytes(&mut self, value: &[u8]) {
        self.put_u64(value.len() as u64);
        self.bytes.extend_from_slice(value);
    }

    pub fn put_str(&mut self, value: &str) {
        self.put_bytes(value.as_bytes());
    }

    pub fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

/// Reads the fields a [`RecordWriter`] wrote; reading past the end is a decode error.
#[derive(Debug)]
pub struct RecordReader<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> RecordReader<'a> {
    pub fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, position: 0 }
    }

    pub fn u64(&mut self) -> Result<u64, StoreDecodeError> {
        let raw: [u8; 8] = self.take(8)?.try_into().map_err(|_| StoreDecodeError)?;
        Ok(u64::from_le_bytes(raw))
    }

    pub fn bytes(&mut self) -> Result<&'a [u8], StoreDecodeError> {
        let length: usize = usize::try_from(self.u64()?).map_err(|_| StoreDecodeError)?;
        self.take(length)
    }

    pub fn string(&mut self) -> Result<String, StoreDecodeError> {
        String::from_utf8(self.bytes()?.to_vec()).map_err(|_| StoreDecodeError)
    }

    pub fn finish(&self) -> Result<(), StoreDecodeError> {
        if self.position == self.bytes.len() {
            Ok(())
        } else {
            Err(StoreDecodeError)
        }
    }

    fn take(&mut self, length: usize) -> Result<&'a [u8], StoreDecodeError> {
        let end: usize = self.position.checked_add(length).ok_or(StoreDecodeError)?;
        let taken: &'a [u8] = self.bytes.get(self.position..end).ok_or(StoreDecodeError)?;
        self.position = end;
        Ok(taken)
    }
}

/// One stored value and the save generation that last used it.
#[derive(Clone, Debug)]
pub(crate) struct StoredValue {
    pub(crate) value: Vec<u8>,
    pub(crate) last_used: u64,
    pub(crate) used: bool,
}

/// One cache kind's entries for one environment; entries are immutable once stored.
#[derive(Debug, Default)]
pub struct NativeStore {
    pub(crate) kind: String,
    pub(crate) environment: String,
    pub(crate) generation: u64,
    pub(crate) metadata: Vec<u8>,
    pub(crate) entries: HashMap<ContentDigest, StoredValue>,
    pub(crate) loaded: usize,
    pub(crate) changed: bool,
}

impl NativeStore {
    /// The caller-owned validation data saved with the loaded entries; empty when none loaded.
    pub fn metadata(&self) -> &[u8] {
        &self.metadata
    }

    /// How many entries the store opened with.
    pub fn loaded_entries(&self) -> usize {
        self.loaded
    }

    /// Drop every loaded entry, for a caller whose metadata check failed.
    pub fn discard(&mut self) {
        self.entries.clear();
        self.metadata.clear();
        self.loaded = 0;
        self.generation = 0;
    }

    /// The value stored under `key`, which the next save keeps.
    pub fn get(&mut self, key: &ContentDigest) -> Option<&[u8]> {
        let stored: &mut StoredValue = self.entries.get_mut(key)?;
        stored.used = true;
        Some(&stored.value)
    }

    /// Store a value computed in this process.
    pub fn put(&mut self, key: ContentDigest, value: Vec<u8>) {
        let stored: StoredValue = StoredValue {
            value,
            last_used: self.generation,
            used: true,
        };
        let _ = self.entries.insert(key, stored);
        self.changed = true;
    }

    /// Whether this process stored a value the file does not hold yet.
    pub fn needs_save(&self) -> bool {
        self.changed
    }

    /// Atomically replace the file with used and recently used entries; returns entries written.
    pub fn save(&self, path: &Path, metadata: &[u8]) -> std::io::Result<usize> {
        let generation: u64 = self.generation + 1;
        let mut entries: Vec<(ContentDigest, u64, Vec<u8>)> = self
            .entries
            .iter()
            .filter(|(_, stored)| {
                stored.used || generation - stored.last_used <= RETAINED_GENERATIONS
            })
            .map(|(key, stored)| {
                let last_used: u64 = if stored.used {
                    generation
                } else {
                    stored.last_used
                };
                (*key, last_used, stored.value.clone())
            })
            .collect();
        entries.sort_unstable_by_key(|(key, _, _)| *key);
        let written: usize = entries.len();
        let bytes: Vec<u8> = encode_store(&StoreFile {
            kind: self.kind.clone(),
            environment: self.environment.clone(),
            generation,
            metadata: metadata.to_vec(),
            entries,
        });
        let directory: &Path = path.parent().unwrap_or_else(|| Path::new("."));
        std::fs::create_dir_all(directory)?;
        let mut file: tempfile::NamedTempFile = tempfile::NamedTempFile::new_in(directory)?;
        file.write_all(&bytes)?;
        let _ = file.persist(path).map_err(|error| error.error)?;
        Ok(written)
    }
}
