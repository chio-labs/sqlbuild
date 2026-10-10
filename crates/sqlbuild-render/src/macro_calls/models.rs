//! Macro call sites, recorded macro call results and the in-compile memo that replays them.

use sqlbuild_cache::digest::main::content_digest::content_digest;
use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::errors::StoreDecodeError;
use sqlbuild_cache::store::models::NativeStore;
use std::collections::HashMap;
use std::sync::Arc;

use crate::macro_calls::_helpers::entry_codec::{decode_entry, encode_entry};

/// One top-level `@macro(...)` call in an authored SQL string; offsets count code points.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroCallSite {
    /// Offset of the `@` that starts the call.
    pub start: usize,
    /// Offset just past the call's closing parenthesis.
    pub end: usize,
    /// The called macro's name.
    pub name: String,
    /// Every macro name in the call, the top-level name first, then nested calls once each;
    /// None where a nested call is not one Python's scan completes.
    pub tree_names: Option<Vec<String>>,
    /// The arguments mention `__ref`, `__source` or `__seed`, so typed references may be passed.
    pub typed_reference_text: bool,
}

/// An error Python's macro call scan raises.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScanError {
    UnclosedQuote,
    UnclosedComment,
    UnclosedParenthesis,
    /// A call start whose name is not followed by its parenthesis.
    MissingParenthesis,
}

impl ScanError {
    /// The message of the `CompileInputError` Python's scan raises.
    pub fn message(self) -> &'static str {
        match self {
            Self::UnclosedQuote => "Macro expansion contains an unclosed quoted string",
            Self::UnclosedComment => "Macro expansion contains an unclosed block comment",
            Self::UnclosedParenthesis => "Macro expansion contains an unclosed parenthesis",
            Self::MissingParenthesis => "expected opening parenthesis",
        }
    }
}

/// Where a scan stops: inside the call at a code point offset, or between calls.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroScanFailure {
    /// Offset of the `@` of the call Python's evaluation raises in, if any.
    pub call_start: Option<usize>,
    pub error: ScanError,
}

/// A string's complete top-level call sites in order, and where the scan stopped, if it did.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroCallScan {
    pub sites: Vec<MacroCallSite>,
    pub failure: Option<MacroScanFailure>,
}

/// One consumer-independent fact a macro call produced, replayed for every consumer in order.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum MacroCallEvent {
    /// A macro, top-level or nested, was resolved and called.
    MacroUse { name: String },
    /// A macro read a constant or enum through its context.
    DeclarationRead { kind: String, name: String },
    /// A macro returned SQL that names typed references, a generated-reference candidate.
    GeneratedSql { macro_name: String, sql: String },
    /// A typed reference was written as a macro argument.
    ArgumentReference { kind: String, name: String },
}

/// The recorded result of one top-level macro call.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroCallEntry {
    /// The macro's SQL before relation placeholders are rendered.
    pub sql: String,
    /// Typed references the call added to the string's relation table, in order.
    pub relations: Vec<(String, String)>,
    /// Facts the call produced, in encounter order.
    pub events: Vec<MacroCallEvent>,
}

/// Substitution offsets of one spliced macro call, in code points.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct MacroSpliceSpan {
    pub source_start: usize,
    pub source_end: usize,
    pub output_start: usize,
    pub output_end: usize,
}

/// One compile's recorded macro call results by class and call text, plus an optional store.
#[derive(Debug, Default)]
pub struct MacroCallMemo {
    entries: HashMap<(u64, String), Arc<MacroCallEntry>>,
    hits: usize,
    misses: usize,
    store: Option<NativeStore>,
    class_digests: HashMap<u64, ContentDigest>,
    store_hits: usize,
    store_records: usize,
}

impl MacroCallMemo {
    /// The recorded result of the call, found in this compile or, if persistent, in the store.
    pub fn lookup(&mut self, class_id: u64, call_text: &str) -> Option<Arc<MacroCallEntry>> {
        let key: (u64, String) = (class_id, call_text.to_owned());
        if let Some(found) = self.entries.get(&key).cloned() {
            self.hits += 1;
            return Some(found);
        }
        match self.stored_entry(class_id, call_text) {
            Some(entry) => {
                self.store_hits += 1;
                let _ = self.entries.insert(key, Arc::clone(&entry));
                Some(entry)
            }
            None => {
                self.misses += 1;
                None
            }
        }
    }

    /// Record the result of one executed call, storing it when its class is persistent.
    pub fn record(&mut self, class_id: u64, call_text: String, entry: MacroCallEntry) {
        if let Some(store_key) = self.store_key(class_id, &call_text)
            && let Some(store) = self.store.as_mut()
        {
            store.put(store_key, encode_entry(&entry));
            self.store_records += 1;
        }
        let _ = self.entries.insert((class_id, call_text), Arc::new(entry));
    }

    /// Lookups that found a recorded result, lookups that did not, and recorded results.
    pub fn stats(&self) -> (usize, usize, usize) {
        (self.hits, self.misses, self.entries.len())
    }

    /// Attach a store whose keys already cover everything every persistent class depends on.
    pub fn attach_store(&mut self, store: NativeStore) {
        self.store = Some(store);
    }

    /// The attached store, if any.
    pub fn store_mut(&mut self) -> Option<&mut NativeStore> {
        self.store.as_mut()
    }

    /// Mark `class_id` persistent under `class_text`, which names all its results depend on.
    pub fn set_persistent_class(&mut self, class_id: u64, class_text: &str) {
        let _ = self
            .class_digests
            .insert(class_id, content_digest(&[class_text]));
    }

    /// Calls found in the store and calls recorded into it.
    pub fn store_stats(&self) -> (usize, usize) {
        (self.store_hits, self.store_records)
    }

    fn stored_entry(&mut self, class_id: u64, call_text: &str) -> Option<Arc<MacroCallEntry>> {
        let store_key: ContentDigest = self.store_key(class_id, call_text)?;
        let bytes: &[u8] = self.store.as_mut()?.get(&store_key)?;
        match decode_entry(bytes) {
            Ok(entry) => Some(Arc::new(entry)),
            Err(StoreDecodeError) => None,
        }
    }

    fn store_key(&self, class_id: u64, call_text: &str) -> Option<ContentDigest> {
        self.store.as_ref()?;
        let class_digest = self.class_digests.get(&class_id)?;
        Some(content_digest(&[
            class_digest.as_slice(),
            call_text.as_bytes(),
        ]))
    }
}
