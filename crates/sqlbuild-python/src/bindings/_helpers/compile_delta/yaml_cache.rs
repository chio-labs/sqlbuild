//! Loaded YAML documents a delta compile keeps by content digest, so the unchanged YAML it
//! reads again is decoded rather than parsed.

use std::path::PathBuf;

use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::models::NativeStore;
use sqlbuild_config::models::{ConfigDate, ConfigDateTime, ConfigTime, ConfigValue};
use sqlbuild_core::text::main::decode_text::decode_text;
use sqlbuild_discovery::yaml_files::models::YamlFileOutcome;

use crate::bindings::_helpers::compile_delta::image_codec::{Decoder, Encoder};

/// The native store kind holding loaded YAML documents.
pub(crate) const YAML_STORE_KIND: &str = "yaml-documents";
/// The store file beside the compile reuse slots.
pub(crate) const YAML_STORE_FILE_NAME: &str = "yaml-documents.bin";
/// Bumped whenever the stored encoding changes; older stores open empty.
pub(crate) const YAML_STORE_ENVIRONMENT: &str = "yaml-documents-v1";

/// Where a delta compile keeps loaded YAML documents.
pub(crate) fn yaml_store_path(cache_dir: &std::path::Path) -> PathBuf {
    cache_dir.join(YAML_STORE_FILE_NAME)
}

/// The store key of a document's text.
pub(crate) fn document_key(contents: &str) -> ContentDigest {
    bytes_digest(contents.as_bytes())
}

const NULL: usize = 0;
const BOOL: usize = 1;
const INTEGER: usize = 2;
const BIG_INTEGER: usize = 3;
const FLOAT: usize = 4;
const STRING: usize = 5;
const DATE: usize = 6;
const DATE_TIME: usize = 7;
const TIME: usize = 8;
const LIST: usize = 9;
const MAP: usize = 10;
const NO_OFFSET: usize = 0;
const OFFSET: usize = 1;

fn put_date(encoder: &mut Encoder<'_>, date: &ConfigDate) {
    encoder.count(usize::from(date.year));
    encoder.count(usize::from(date.month));
    encoder.count(usize::from(date.day));
}

fn put_time(encoder: &mut Encoder<'_>, time: &ConfigTime) {
    encoder.count(usize::from(time.hour));
    encoder.count(usize::from(time.minute));
    encoder.count(usize::from(time.second));
    encoder.bytes(&time.microsecond.to_le_bytes());
}

fn put_value<'a>(encoder: &mut Encoder<'a>, value: &'a ConfigValue) {
    match value {
        ConfigValue::Null => encoder.count(NULL),
        ConfigValue::Bool(flag) => {
            encoder.count(BOOL);
            encoder.flag(*flag);
        }
        ConfigValue::Integer(number) => {
            encoder.count(INTEGER);
            encoder.bytes(&number.to_le_bytes());
        }
        ConfigValue::BigInteger(digits) => {
            encoder.count(BIG_INTEGER);
            encoder.string(digits);
        }
        ConfigValue::Float(number) => {
            encoder.count(FLOAT);
            encoder.bytes(&number.to_bits().to_le_bytes());
        }
        ConfigValue::String(text) => {
            encoder.count(STRING);
            encoder.string(text);
        }
        ConfigValue::Date(date) => {
            encoder.count(DATE);
            put_date(encoder, date);
        }
        ConfigValue::DateTime(moment) => {
            encoder.count(DATE_TIME);
            put_date(encoder, &moment.date);
            put_time(encoder, &moment.time);
            match moment.utc_offset_seconds {
                Some(offset) => {
                    encoder.count(OFFSET);
                    encoder.bytes(&offset.to_le_bytes());
                }
                None => encoder.count(NO_OFFSET),
            }
        }
        ConfigValue::Time(time) => {
            encoder.count(TIME);
            put_time(encoder, time);
        }
        ConfigValue::List(items) => {
            encoder.count(LIST);
            encoder.count(items.len());
            for item in items {
                put_value(encoder, item);
            }
        }
        ConfigValue::Map(entries) => {
            encoder.count(MAP);
            encoder.count(entries.len());
            for (key, item) in entries {
                put_value(encoder, key);
                put_value(encoder, item);
            }
        }
    }
}

/// A loaded document as stored.
pub(crate) fn encoded_document(value: &ConfigValue) -> Vec<u8> {
    let mut encoder: Encoder<'_> = Encoder::default();
    put_value(&mut encoder, value);
    encoder.finish()
}

fn fixed<const N: usize>(decoder: &mut Decoder<'_>) -> Option<[u8; N]> {
    decoder.bytes()?.try_into().ok()
}

fn small<T: TryFrom<usize>>(decoder: &mut Decoder<'_>) -> Option<T> {
    T::try_from(decoder.count()?).ok()
}

fn date(decoder: &mut Decoder<'_>) -> Option<ConfigDate> {
    Some(ConfigDate {
        year: small(decoder)?,
        month: small(decoder)?,
        day: small(decoder)?,
    })
}

fn time(decoder: &mut Decoder<'_>) -> Option<ConfigTime> {
    Some(ConfigTime {
        hour: small(decoder)?,
        minute: small(decoder)?,
        second: small(decoder)?,
        microsecond: u32::from_le_bytes(fixed(decoder)?),
    })
}

fn value(decoder: &mut Decoder<'_>) -> Option<ConfigValue> {
    Some(match decoder.count()? {
        NULL => ConfigValue::Null,
        BOOL => ConfigValue::Bool(decoder.flag()?),
        INTEGER => ConfigValue::Integer(i64::from_le_bytes(fixed(decoder)?)),
        BIG_INTEGER => ConfigValue::BigInteger(decoder.string()?),
        FLOAT => ConfigValue::Float(f64::from_bits(u64::from_le_bytes(fixed(decoder)?))),
        STRING => ConfigValue::String(decoder.string()?),
        DATE => ConfigValue::Date(date(decoder)?),
        DATE_TIME => ConfigValue::DateTime(ConfigDateTime {
            date: date(decoder)?,
            time: time(decoder)?,
            utc_offset_seconds: match decoder.count()? {
                NO_OFFSET => None,
                OFFSET => Some(i32::from_le_bytes(fixed(decoder)?)),
                _ => return None,
            },
        }),
        TIME => ConfigValue::Time(time(decoder)?),
        LIST => ConfigValue::List(decoder.list(value)?),
        MAP => ConfigValue::Map(decoder.list(|decoder| Some((value(decoder)?, value(decoder)?)))?),
        _ => return None,
    })
}

/// A stored document, or `None` when it cannot be decoded.
pub(crate) fn decoded_document(stored: &[u8]) -> Option<ConfigValue> {
    let mut decoder: Decoder<'_> = Decoder::new(stored)?;
    let document: ConfigValue = value(&mut decoder)?;
    decoder.finish()?;
    Some(document)
}

/// The store a delta compile reads and fills, opened beside its reuse slots.
pub(crate) struct DocumentStore {
    pub(crate) store: NativeStore,
    pub(crate) path: PathBuf,
}

/// In a delta compile, the document store beside its reuse slots; `None` otherwise or when it
/// cannot be opened, which only means parsing again.
pub(crate) fn open_documents(py: pyo3::Python<'_>) -> Option<DocumentStore> {
    let path: PathBuf = crate::bindings::_helpers::compile_delta::context::injection()?
        .yaml_store
        .clone()?;
    let store: NativeStore = crate::bindings::_helpers::cache::native_store::open_store(
        py,
        &path,
        YAML_STORE_KIND,
        YAML_STORE_ENVIRONMENT,
    )
    .ok()?;
    Some(DocumentStore { store, path })
}

/// Save the documents this compile loaded; failing to only means parsing them again.
pub(crate) fn save_documents(py: pyo3::Python<'_>, documents: &DocumentStore) {
    let _ = crate::bindings::_helpers::cache::native_store::save_store(
        py,
        &documents.store,
        &documents.path,
        &[],
    );
}

/// Each file's loaded document: decoded from `documents` when its text is stored, otherwise
/// loaded by `load` and stored.
pub(crate) fn load_with<E>(
    documents: &mut DocumentStore,
    paths: &[String],
    absolute: impl Fn(&str) -> PathBuf,
    load: impl FnOnce(&[String]) -> Result<Vec<YamlFileOutcome>, E>,
) -> Result<Vec<YamlFileOutcome>, E> {
    let mut outcomes: Vec<Option<YamlFileOutcome>> = Vec::with_capacity(paths.len());
    let mut missed: Vec<String> = Vec::new();
    for path in paths {
        let stored: Option<YamlFileOutcome> = std::fs::read(absolute(path))
            .ok()
            .and_then(|bytes| decode_text(&bytes).ok())
            .and_then(|contents| {
                let value: ConfigValue =
                    decoded_document(documents.store.get(&document_key(&contents))?)?;
                Some(YamlFileOutcome::Loaded { contents, value })
            });
        if stored.is_none() {
            missed.push(path.clone());
        }
        outcomes.push(stored);
    }
    let mut loaded = if missed.is_empty() {
        Vec::new()
    } else {
        load(&missed)?
    }
    .into_iter();
    let mut complete: Vec<YamlFileOutcome> = Vec::with_capacity(paths.len());
    for outcome in outcomes {
        let outcome: YamlFileOutcome = match outcome {
            Some(outcome) => outcome,
            None => {
                let Some(outcome) = loaded.next() else {
                    break;
                };
                if let YamlFileOutcome::Loaded { contents, value } = &outcome {
                    documents
                        .store
                        .put(document_key(contents), encoded_document(value));
                }
                outcome
            }
        };
        complete.push(outcome);
    }
    Ok(complete)
}
