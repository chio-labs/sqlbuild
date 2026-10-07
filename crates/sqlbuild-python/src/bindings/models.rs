//! Python-facing classes and mapping requests, converted to native models at the boundary.

use pyo3::{FromPyObject, pyclass};
use sqlbuild_analysis::semantic_validation::models as validation;
use sqlbuild_analysis::semantic_validation::types::{Expansion, Relations};
use sqlbuild_rules::models::EvaluateRequest;
use std::collections::HashMap;
use std::sync::Mutex;

/// A decoded rules request held natively so the caller can release its encoded payloads.
#[pyclass(module = "sqlbuild._native")]
#[derive(Debug)]
pub(crate) struct ParsedRulesRequest {
    pub(crate) request: Mutex<Option<EvaluateRequest>>,
}

#[derive(FromPyObject, Debug)]
#[pyo3(from_item_all)]
pub(crate) struct CatalogInput {
    pub(crate) dialect: String,
    pub(crate) quoted_ignore_case: bool,
    pub(crate) known_functions: Vec<String>,
    pub(crate) known_types: Vec<String>,
    #[pyo3(from_py_with = crate::bindings::_helpers::conversions::relations)]
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
#[derive(Debug)]
pub(crate) struct ProjectCatalog {
    pub(crate) inner: validation::ProjectCatalog,
}

/// One resolved compact analysis batch that runs without borrowing its project catalog.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct CompactAnalysisJob {
    pub(crate) inner: validation::CompactAnalysisJob,
}

#[pyclass(module = "sqlbuild._native")]
#[derive(Debug)]
pub(crate) struct BindingPositions {
    pub(crate) inner: validation::BindingPositions,
}

impl From<CatalogInput> for validation::CatalogInput {
    fn from(input: CatalogInput) -> Self {
        Self {
            dialect: input.dialect,
            quoted_ignore_case: input.quoted_ignore_case,
            known_functions: input.known_functions,
            known_types: input.known_types,
            relations: input.relations,
        }
    }
}

impl From<NormalizationInput> for validation::NormalizationInput {
    fn from(input: NormalizationInput) -> Self {
        Self {
            sql: input.sql,
            dialect: input.dialect,
            stubs: input.stubs,
            placeholders: input.placeholders,
        }
    }
}

impl From<PositionInput> for validation::PositionInput {
    fn from(input: PositionInput) -> Self {
        Self {
            authored: input.authored,
            query: input.query,
            expanded: input.expanded,
            cleaned: input.cleaned,
            passes: input.passes,
        }
    }
}

/// The directory listings one Python discovery pass shares across its native calls.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug)]
pub(crate) struct NativeProjectTree {
    pub(crate) inner: sqlbuild_discovery::tree::models::ProjectTree,
    /// Directories whose listings were already handed to the Python snapshot.
    pub(crate) exported: Mutex<std::collections::HashSet<String>>,
}

/// One native model discovery request from the Python discovery facade.
#[derive(FromPyObject, Debug)]
#[pyo3(from_item_all)]
pub(crate) struct ModelDiscoveryRequest {
    pub(crate) project_dir: String,
    pub(crate) display_prefix: String,
    pub(crate) supported_keys: Vec<String>,
    pub(crate) removed_keys: Vec<String>,
    pub(crate) extract_implicit_alias_columns: bool,
    pub(crate) extract_output_column_locations: bool,
}
