//! Compile-owned native catalog, mapping state and Python-boundary requests.

use crate::semantic_validation::types::{Expansion, Relations};
use polyglot_sql::validation::SchemaTable;
use polyglot_sql::{DialectType, SchemaValidationOptions};
use pyo3::{FromPyObject, pyclass};
use std::collections::HashMap;

#[derive(Default, Debug)]
pub(crate) struct Columns(pub(crate) Vec<(String, Option<String>)>);

#[derive(FromPyObject, Debug)]
#[pyo3(from_item_all)]
pub(crate) struct CatalogInput {
    pub(crate) dialect: String,
    pub(crate) quoted_ignore_case: bool,
    pub(crate) known_functions: Vec<String>,
    pub(crate) known_types: Vec<String>,
    pub(crate) relations: Relations,
}

#[derive(FromPyObject, Debug)]
#[pyo3(from_item_all)]
pub(crate) struct NormalizationInput {
    pub(crate) sql: String,
    pub(crate) dialect: String,
    pub(crate) stubs: HashMap<String, String>,
    pub(crate) placeholders: HashMap<String, String>,
}

#[derive(FromPyObject, Debug)]
#[pyo3(from_item_all)]
pub(crate) struct PositionInput {
    pub(crate) authored: String,
    pub(crate) query: String,
    pub(crate) expanded: String,
    pub(crate) cleaned: String,
    pub(crate) passes: Vec<Vec<Expansion>>,
}

#[pyclass(module = "sqlbuild._native")]
pub(crate) struct ProjectCatalog {
    pub(crate) dialect: DialectType,
    pub(crate) options: SchemaValidationOptions,
    pub(crate) quoted_ignore_case: bool,
    pub(super) tables: HashMap<String, SchemaTable>,
    pub(super) overrides: Vec<HashMap<String, SchemaTable>>,
    pub(super) analysis_tables: HashMap<String, SchemaTable>,
}

#[pyclass(module = "sqlbuild._native")]
#[derive(Debug)]
pub(crate) struct BindingPositions {
    pub(super) authored: String,
    pub(super) query_start: Option<usize>,
    pub(super) lines: Vec<usize>,
    pub(super) cleaned_lines: Vec<usize>,
    pub(super) offsets: Vec<usize>,
    pub(super) passes: Vec<Vec<Expansion>>,
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
