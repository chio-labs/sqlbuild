//! Open one cache kind's store file.

use std::collections::HashMap;
use std::path::Path;

use crate::store::_helpers::frame::{StoreFile, decode_store};
use crate::store::errors::StoreDecodeError;
use crate::store::models::{NativeStore, StoredValue};

/// Load `kind` entries for exactly `environment`; missing, damaged or foreign files open empty.
pub fn open_native_store(
    path: &Path,
    kind: &str,
    environment: &str,
) -> std::io::Result<NativeStore> {
    let mut store: NativeStore = NativeStore {
        kind: kind.to_owned(),
        environment: environment.to_owned(),
        ..NativeStore::default()
    };
    let bytes: Vec<u8> = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(store),
        Err(error) => return Err(error),
    };
    let file: StoreFile = match decode_store(&bytes) {
        Ok(file) if file.kind == kind && file.environment == environment => file,
        Ok(_) | Err(StoreDecodeError) => return Ok(store),
    };
    store.generation = file.generation;
    store.metadata = file.metadata;
    store.loaded = file.entries.len();
    store.entries = file
        .entries
        .into_iter()
        .map(|(key, last_used, value)| {
            let stored: StoredValue = StoredValue {
                value,
                last_used,
                used: false,
            };
            (key, stored)
        })
        .collect::<HashMap<_, _>>();
    Ok(store)
}
