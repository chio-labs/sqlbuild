//! Encode and verify whole store files.

use crate::digest::main::content_digest::content_digest;
use crate::digest::types::ContentDigest;
use crate::store::constants::{STORE_FORMAT_VERSION, STORE_MAGIC};
use crate::store::errors::StoreDecodeError;
use crate::store::models::{RecordReader, RecordWriter};

/// The decoded contents of one store file.
pub(crate) struct StoreFile {
    pub(crate) kind: String,
    pub(crate) environment: String,
    pub(crate) generation: u64,
    pub(crate) metadata: Vec<u8>,
    pub(crate) entries: Vec<(ContentDigest, u64, Vec<u8>)>,
}

/// Magic, format version, a digest of the body, then the body.
pub(crate) fn encode_store(file: &StoreFile) -> Vec<u8> {
    let mut body: RecordWriter = RecordWriter::default();
    body.put_str(&file.kind);
    body.put_str(&file.environment);
    body.put_u64(file.generation);
    body.put_bytes(&file.metadata);
    body.put_u64(file.entries.len() as u64);
    for (key, last_used, value) in &file.entries {
        body.put_bytes(key);
        body.put_u64(*last_used);
        body.put_bytes(value);
    }
    let body: Vec<u8> = body.into_bytes();
    let mut bytes: Vec<u8> = Vec::with_capacity(body.len() + 44);
    bytes.extend_from_slice(STORE_MAGIC);
    bytes.extend_from_slice(&STORE_FORMAT_VERSION.to_le_bytes());
    bytes.extend_from_slice(&content_digest(&[&body]));
    bytes.extend_from_slice(&body);
    bytes
}

/// The file's contents; another format, a damaged body or trailing bytes are decode errors.
pub(crate) fn decode_store(bytes: &[u8]) -> Result<StoreFile, StoreDecodeError> {
    let rest: &[u8] = bytes
        .strip_prefix(STORE_MAGIC.as_slice())
        .ok_or(StoreDecodeError)?;
    let (version, rest) = rest.split_first_chunk::<4>().ok_or(StoreDecodeError)?;
    if u32::from_le_bytes(*version) != STORE_FORMAT_VERSION {
        return Err(StoreDecodeError);
    }
    let (checksum, body) = rest.split_first_chunk::<32>().ok_or(StoreDecodeError)?;
    if content_digest(&[body]) != *checksum {
        return Err(StoreDecodeError);
    }
    let mut reader: RecordReader<'_> = RecordReader::new(body);
    let kind: String = reader.string()?;
    let environment: String = reader.string()?;
    let generation: u64 = reader.u64()?;
    let metadata: Vec<u8> = reader.bytes()?.to_vec();
    let count: u64 = reader.u64()?;
    let mut entries: Vec<(ContentDigest, u64, Vec<u8>)> = Vec::new();
    for _ in 0..count {
        let key: ContentDigest = reader.bytes()?.try_into().map_err(|_| StoreDecodeError)?;
        let last_used: u64 = reader.u64()?;
        let value: Vec<u8> = reader.bytes()?.to_vec();
        entries.push((key, last_used, value));
    }
    reader.finish()?;
    Ok(StoreFile {
        kind,
        environment,
        generation,
        metadata,
        entries,
    })
}
