//! Macro call sites, recorded macro call results and the in-compile memo that replays them.

use std::collections::HashMap;
use std::sync::Arc;

/// One top-level `@macro(...)` call in an authored SQL string; offsets count code points.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroCallSite {
    /// Offset of the `@` that starts the call.
    pub start: usize,
    /// Offset just past the call's closing parenthesis.
    pub end: usize,
    /// The called macro's name.
    pub name: String,
    /// Every macro name in the call, the top-level name first, then nested calls once each.
    pub tree_names: Vec<String>,
    /// The arguments mention `__ref`, `__source` or `__seed`, so typed references may be passed.
    pub typed_reference_text: bool,
}

/// The scan met text Python reports or classifies differently; Python must expand the string.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ScanDeferral;

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

/// Recorded macro call results of one compile, keyed by call class and exact call text.
#[derive(Debug, Default)]
pub struct MacroCallMemo {
    entries: HashMap<(u64, String), Arc<MacroCallEntry>>,
    hits: usize,
    misses: usize,
}

impl MacroCallMemo {
    /// Return the recorded result for the call, counting the lookup as a hit or a miss.
    pub fn lookup(&mut self, class_id: u64, call_text: &str) -> Option<Arc<MacroCallEntry>> {
        let found = self.entries.get(&(class_id, call_text.to_owned())).cloned();
        if found.is_some() {
            self.hits += 1;
        } else {
            self.misses += 1;
        }
        found
    }

    /// Record the result of one executed call.
    pub fn record(&mut self, class_id: u64, call_text: String, entry: MacroCallEntry) {
        let _ = self.entries.insert((class_id, call_text), Arc::new(entry));
    }

    /// Lookups that found a recorded result, lookups that did not, and recorded results.
    pub fn stats(&self) -> (usize, usize, usize) {
        (self.hits, self.misses, self.entries.len())
    }
}
