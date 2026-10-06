//! Compile-owned native catalog, mapping state and boundary requests.

use crate::semantic_validation::types::{Expansion, PreparedCompactAnalysis, ProbeKey, Relations};
use polyglot_sql::validation::SchemaTable;
use polyglot_sql::{DialectType, SchemaValidationOptions};
use rayon::ThreadPool;
use std::collections::HashMap;
use std::sync::atomic::AtomicUsize;
use std::sync::{Arc, Mutex};

#[derive(Default, Debug)]
pub struct Columns(pub Vec<(String, Option<String>)>);

#[derive(Debug)]
pub struct CatalogInput {
    pub dialect: String,
    pub quoted_ignore_case: bool,
    pub known_functions: Vec<String>,
    pub known_types: Vec<String>,
    pub relations: Relations,
}

#[derive(Debug)]
pub struct NormalizationInput {
    pub sql: String,
    pub dialect: String,
    pub stubs: HashMap<String, String>,
    pub placeholders: HashMap<String, String>,
}

#[derive(Debug)]
pub struct PositionInput {
    pub authored: String,
    pub query: String,
    pub expanded: String,
    pub cleaned: String,
    pub passes: Vec<Vec<Expansion>>,
}

/// Memoized call-site function-name probes, owned by the catalog that validates a compile.
#[derive(Debug, Default)]
pub(crate) struct FunctionProbes {
    pub(crate) suggestions: Mutex<HashMap<ProbeKey, Option<String>>>,
}

pub struct ProjectCatalog {
    pub(crate) dialect: DialectType,
    pub(crate) options: SchemaValidationOptions,
    pub(crate) quoted_ignore_case: bool,
    pub(super) tables: HashMap<String, SchemaTable>,
    pub(super) overrides: Vec<HashMap<String, SchemaTable>>,
    pub(super) analysis_tables: HashMap<String, SchemaTable>,
    pub(crate) function_probes: Arc<FunctionProbes>,
    /// One analysis pool per compile catalog, built on first use and shared by its views.
    pub(super) analysis_pool: Arc<Mutex<Option<Arc<ThreadPool>>>>,
    /// Analysis batches running on the pool; preparation only borrows the pool while none run.
    pub(super) running_analyses: Arc<AtomicUsize>,
}

/// One resolved compact analysis batch that runs without borrowing its project catalog.
pub struct CompactAnalysisJob {
    pub(super) analysis: Mutex<Option<PreparedCompactAnalysis>>,
    pub(super) catalog: ProjectCatalog,
}

#[derive(Debug)]
pub struct BindingPositions {
    pub(super) authored: String,
    pub(super) query_start: Option<usize>,
    pub(super) lines: Vec<usize>,
    pub(super) cleaned_lines: Vec<usize>,
    pub(super) offsets: Vec<usize>,
    pub(super) passes: Vec<Vec<Expansion>>,
    pub(super) words: std::sync::OnceLock<HashMap<String, (usize, bool)>>,
}

impl std::fmt::Debug for ProjectCatalog {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("ProjectCatalog")
            .field("dialect", &self.dialect)
            .field("quoted_ignore_case", &self.quoted_ignore_case)
            .field("relation_count", &self.tables.len())
            .finish_non_exhaustive()
    }
}
