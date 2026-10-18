//! Files of named, separately checksummed sections that readers may skip or carry forward.

use std::io::Write;
use std::path::Path;

use crate::digest::main::bytes_digest::bytes_digest;
use crate::digest::types::ContentDigest;
use crate::store::errors::StoreDecodeError;
use crate::store::models::{RecordReader, RecordWriter};

const MAGIC: &[u8; 8] = b"SQBREUSE";
const FORMAT_VERSION: u32 = 1;
const DIGEST_BYTES: usize = 32;

/// One file's sections in stored order and the digest identifying the file.
#[derive(Debug)]
pub(crate) struct SectionFile<'a> {
    pub(crate) identity: ContentDigest,
    pub(crate) sections: Vec<(String, &'a [u8])>,
}

impl<'a> SectionFile<'a> {
    /// The bytes of the section called `name`.
    pub(crate) fn section(&self, name: &str) -> Option<&'a [u8]> {
        self.sections
            .iter()
            .find(|(section, _)| section == name)
            .map(|(_, bytes)| *bytes)
    }
}

/// Encode `sections` for `role`; returns the bytes and the file identity.
pub(crate) fn encode_sections(role: &str, sections: &[(&str, &[u8])]) -> (Vec<u8>, ContentDigest) {
    let mut header: RecordWriter = RecordWriter::default();
    header.put_str(role);
    header.put_u64(sections.len() as u64);
    for (name, bytes) in sections {
        header.put_str(name);
        header.put_u64(bytes.len() as u64);
        header.put_bytes(&bytes_digest(bytes));
    }
    let header: Vec<u8> = header.into_bytes();
    let identity: ContentDigest = bytes_digest(&header);
    let payload: usize = sections.iter().map(|(_, bytes)| bytes.len()).sum();
    let mut encoded: Vec<u8> =
        Vec::with_capacity(MAGIC.len() + 12 + header.len() + DIGEST_BYTES + payload);
    encoded.extend_from_slice(MAGIC);
    encoded.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
    encoded.extend_from_slice(&(header.len() as u64).to_le_bytes());
    encoded.extend_from_slice(&header);
    encoded.extend_from_slice(&identity);
    for (_, bytes) in sections {
        encoded.extend_from_slice(bytes);
    }
    (encoded, identity)
}

/// The verified sections of a `role` file; any other format, role or damage is a decode error.
pub(crate) fn decode_sections<'a>(
    bytes: &'a [u8],
    role: &str,
) -> Result<SectionFile<'a>, StoreDecodeError> {
    let rest: &[u8] = bytes
        .strip_prefix(MAGIC.as_slice())
        .ok_or(StoreDecodeError)?;
    let (version, rest) = rest.split_first_chunk::<4>().ok_or(StoreDecodeError)?;
    if u32::from_le_bytes(*version) != FORMAT_VERSION {
        return Err(StoreDecodeError);
    }
    let (length, rest) = rest.split_first_chunk::<8>().ok_or(StoreDecodeError)?;
    let length: usize =
        usize::try_from(u64::from_le_bytes(*length)).map_err(|_| StoreDecodeError)?;
    let header: &[u8] = rest.get(..length).ok_or(StoreDecodeError)?;
    let (identity, mut payload) = rest[length..]
        .split_first_chunk::<DIGEST_BYTES>()
        .ok_or(StoreDecodeError)?;
    if bytes_digest(header) != *identity {
        return Err(StoreDecodeError);
    }
    let mut reader: RecordReader<'_> = RecordReader::new(header);
    if reader.string()? != role {
        return Err(StoreDecodeError);
    }
    let count: u64 = reader.u64()?;
    let mut sections: Vec<(String, &'a [u8])> = Vec::new();
    for _ in 0..count {
        let name: String = reader.string()?;
        let size: usize = usize::try_from(reader.u64()?).map_err(|_| StoreDecodeError)?;
        let digest: &[u8] = reader.bytes()?;
        if size > payload.len() {
            return Err(StoreDecodeError);
        }
        let (section, remaining) = payload.split_at(size);
        if bytes_digest(section).as_slice() != digest {
            return Err(StoreDecodeError);
        }
        sections.push((name, section));
        payload = remaining;
    }
    reader.finish()?;
    if !payload.is_empty() {
        return Err(StoreDecodeError);
    }
    Ok(SectionFile {
        identity: *identity,
        sections,
    })
}

/// Replace `path` with `bytes` through a temporary file in the same folder.
pub(crate) fn write_atomically(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    let directory: &Path = path.parent().unwrap_or_else(|| Path::new("."));
    std::fs::create_dir_all(directory)?;
    let mut file: tempfile::NamedTempFile = tempfile::NamedTempFile::new_in(directory)?;
    file.write_all(bytes)?;
    let _ = file.persist(path).map_err(|error| error.error)?;
    Ok(())
}
