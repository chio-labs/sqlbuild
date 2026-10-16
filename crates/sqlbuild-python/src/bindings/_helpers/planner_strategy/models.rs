//! Extension-owned fixture analysis reuse and the project-wide fixture planning context.

use std::collections::{BTreeSet, HashMap};
use std::sync::{Arc, Mutex};

use pyo3::prelude::Py;
use pyo3::pyclass;
use pyo3::types::{PyAny, PyDict};
use sqlbuild_analysis::planner_fixtures::models::{
    FixtureColumn, FixtureReadCache, FixtureTypeProjection,
};
use sqlbuild_analysis::required_columns::models::ColumnRead;

use crate::bindings::_helpers::planner_strategy::types::FixtureKey;

/// Per-extension cache replacing the Python fixture resolver's LRU.
#[pyclass]
#[derive(Debug, Default)]
pub(crate) struct FixtureReadCacheHost {
    pub(crate) cache: FixtureReadCache,
    /// Fixture planning contexts built since the last reset.
    pub(crate) context_builds: u64,
    /// SQL-test model chain batches resolved since the last reset.
    pub(crate) chain_resolutions: u64,
}

/// One relation's known fixture columns and whether they form an authoritative shape.
#[derive(Clone, Debug)]
pub(crate) struct FixtureRelation {
    pub(crate) columns: Vec<FixtureColumn>,
    pub(crate) authoritative: bool,
}

/// One model's high-confidence lineage reads and direct type projections.
#[derive(Debug)]
pub(crate) struct ModelFixtureFacts {
    pub(crate) reads: Vec<ColumnRead>,
    pub(crate) projections: Vec<FixtureTypeProjection>,
}

/// Project-wide fixture metadata shared across test and scenario planning.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug)]
pub(crate) struct RelationFixturePlanningContext {
    pub(crate) models_by_name: Py<PyDict>,
    pub(crate) relations: HashMap<FixtureKey, FixtureRelation>,
    pub(crate) authoritative_columns: HashMap<FixtureKey, BTreeSet<String>>,
    pub(crate) expected_types: HashMap<FixtureKey, Vec<(String, String)>>,
    pub(crate) fixture_inferences: Py<PyAny>,
    pub(crate) model_facts: Mutex<HashMap<String, Arc<ModelFixtureFacts>>>,
}

/// The expected column types of one completion: its chain's propagated types over the context's.
#[derive(Debug)]
pub(crate) struct ExpectedTypes<'a> {
    pub(crate) overlay: Vec<(FixtureKey, Vec<(String, String)>)>,
    pub(crate) base: &'a HashMap<FixtureKey, Vec<(String, String)>>,
}
