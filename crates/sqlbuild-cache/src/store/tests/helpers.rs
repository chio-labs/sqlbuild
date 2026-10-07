use std::path::Path;

use crate::digest::main::content_digest::content_digest;
use crate::digest::types::ContentDigest;
use crate::store::errors::StoreDecodeError;
use crate::store::main::open_native_store::open_native_store;
use crate::store::models::{NativeStore, RecordReader, RecordWriter};

pub(crate) const KIND: &str = "macro-calls";
pub(crate) const ENVIRONMENT: &str = "environment-a";
pub(crate) const METADATA: &[u8] = b"module stamps";
pub(crate) const VALUE: &[u8] = b"amount * 100";

pub(crate) fn key(text: &str) -> ContentDigest {
    content_digest(&[text])
}

pub(crate) fn open(path: &Path) -> NativeStore {
    open_native_store(path, KIND, ENVIRONMENT).expect("opened store")
}

/// Save a store holding `VALUE` under the `cents` key.
pub(crate) fn saved_store(path: &Path) {
    let mut store = open(path);
    store.put(key("cents"), VALUE.to_vec());
    assert_eq!(store.save(path, METADATA).expect("saved"), 1);
}

/// Flip one byte near the end of the file.
pub(crate) fn damage(path: &Path) {
    let mut bytes = std::fs::read(path).expect("store bytes");
    let last = bytes.len() - 1;
    bytes[last] ^= 0xff;
    std::fs::write(path, bytes).expect("damaged store");
}

/// A record holding a string and a number.
pub(crate) fn record() -> Vec<u8> {
    let mut writer = RecordWriter::default();
    writer.put_str("café");
    writer.put_u64(7);
    writer.into_bytes()
}

/// Read a string and a number, then require the end of the record.
pub(crate) fn read_record(bytes: &[u8]) -> Result<(String, u64), StoreDecodeError> {
    let mut reader = RecordReader::new(bytes);
    let text = reader.string()?;
    let number = reader.u64()?;
    reader.finish()?;
    Ok((text, number))
}
