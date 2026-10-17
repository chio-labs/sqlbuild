//! What each model's native header values show before the ordered loop, read off the GIL.
//!
//! The ordered loop uses a fact only for a config value that is the header's own object, so a
//! value that path defaults, templates or hooks replaced is still read from Python.

use std::sync::{Arc, OnceLock};

use pyo3::prelude::PyAnyMethods;
use pyo3::prelude::{Bound, PyAny, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods};
use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use rayon::{ThreadPool, ThreadPoolBuilder};
use sqlbuild_model_config::config_presence::main::blocks_config_reuse::blocks_config_reuse;
use sqlbuild_model_config::config_presence::main::contains_template::contains_template;
use sqlbuild_model_config::config_presence::main::entry_macro_path::entry_macro_path;
use sqlbuild_model_config::config_presence::models::MacroPath;
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::bindings::_helpers::model_config::header_metadata::NativeColumn;
use crate::bindings::_helpers::model_config::native_nodes::{NativeNode, dict_entries, exactly};

const COLUMNS_KEY: &str = "columns";
/// The compile pools' fixed worker count.
const PREPASS_WORKERS: usize = 4;
const WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

static NULL_VALUE: AuthoredValue = AuthoredValue::Null;
static POOL: OnceLock<Result<ThreadPool, String>> = OnceLock::new();

/// What one top-level header entry holds, as the config checks walk it.
pub(crate) struct EntryFacts {
    /// Whether a string in the value holds a `${...}` template.
    pub(crate) template: bool,
    /// Where `first_macro_path` finds a macro call in this entry.
    pub(crate) macro_path: MacroPath,
    /// Whether the value keeps the model from reusing another model's config.
    pub(crate) blocks_reuse: bool,
}

/// One model's header facts, read from its native authored values.
pub(crate) struct HeaderFacts {
    /// Each header key in the projected dict's order, with its facts.
    entries: Vec<(String, EntryFacts)>,
    /// The header's columns, when they parse without an error.
    pub(crate) columns: Option<Vec<NativeColumn>>,
}

impl HeaderFacts {
    /// The facts of `key`'s value in the header.
    pub(crate) fn entry(&self, key: &str) -> Option<&EntryFacts> {
        self.entries
            .iter()
            .find(|(name, _)| name == key)
            .map(|(_, facts)| facts)
    }

    /// The facts of a config entry, when its value is the header's own value of `key`.
    pub(crate) fn own_entry<'py>(
        &self,
        header: &Bound<'py, PyDict>,
        key: &Bound<'py, PyAny>,
        value: &Bound<'py, PyAny>,
    ) -> PyResult<Option<&EntryFacts>> {
        let Ok(name) = key.downcast::<PyString>() else {
            return Ok(None);
        };
        let Ok(name) = name.to_str() else {
            return Ok(None);
        };
        let Some(facts) = self.entry(name) else {
            return Ok(None);
        };
        Ok(header
            .get_item(name)?
            .filter(|own| own.is(value))
            .map(|_| facts))
    }
}

/// The header facts of one model's native authored values; `path` names it in parse messages.
pub(crate) fn header_facts(values: &[(String, AuthoredValue)], path: &str) -> HeaderFacts {
    let entries: Vec<(String, EntryFacts)> = dict_entries(values)
        .into_iter()
        .map(|(key, value)| {
            let node: NativeNode<'_> = NativeNode::Value(value);
            (
                key.to_owned(),
                EntryFacts {
                    template: contains_template(&node),
                    macro_path: entry_macro_path(&NativeNode::Key(key), &node),
                    blocks_reuse: blocks_config_reuse(&node),
                },
            )
        })
        .collect();
    let columns: Option<Vec<NativeColumn>> = dict_entries(values)
        .into_iter()
        .find(|(key, _)| *key == COLUMNS_KEY)
        .map(|(_, value)| value)
        .filter(|value| **value != AuthoredValue::Null)
        .and_then(|value| {
            let (metadata, exact) = exactly(|| {
                parse_header_metadata(
                    &NativeNode::Value(value),
                    &NativeNode::Value(&NULL_VALUE),
                    path,
                )
            });
            let columns = metadata.columns.ok().filter(|_| exact)?;
            Some(columns.iter().map(NativeColumn::parsed).collect())
        });
    HeaderFacts { entries, columns }
}

/// Each model's header facts, computed on the compile pool; `None` where no native header exists.
pub(crate) fn all_header_facts(
    headers: &[Option<(Arc<[(String, AuthoredValue)]>, String)>],
) -> Result<Vec<Option<HeaderFacts>>, String> {
    let read = || -> Vec<Option<HeaderFacts>> {
        headers
            .par_iter()
            .map(|header| {
                header
                    .as_ref()
                    .map(|(values, path)| header_facts(values, path))
            })
            .collect()
    };
    let pool: &ThreadPool = POOL
        .get_or_init(|| {
            ThreadPoolBuilder::new()
                .num_threads(PREPASS_WORKERS)
                .stack_size(WORKER_STACK_BYTES)
                .thread_name(|index| format!("sqlbuild-model-prepass-{index}"))
                .build()
                .map_err(|error| error.to_string())
        })
        .as_ref()
        .map_err(Clone::clone)?;
    Ok(pool.install(read))
}
