//! PoC-only pure-Rust facade over the native analysis catalog (feature `poc`, never shipped).

use crate::semantic_validation::models::{CatalogInput, Columns, ProjectCatalog};
use crate::semantic_validation::types::PreparedCompactAnalysis;
use std::collections::HashMap;
use std::sync::Arc;

pub type Cols = Vec<(String, Option<String>)>;
pub type Relations = Vec<(String, Cols)>;
pub type DiagnosticRow = (
    String,
    String,
    Option<usize>,
    Option<usize>,
    Option<usize>,
    Option<usize>,
    String,
);
pub type BindingRequest = (String, Vec<(String, bool)>, Relations);
pub type NormalizationRequest = (String, HashMap<String, String>, HashMap<String, String>);

fn relations(value: Relations) -> HashMap<String, Columns> {
    value
        .into_iter()
        .map(|(name, columns)| (name, Columns(columns)))
        .collect()
}

pub struct Catalog {
    inner: ProjectCatalog,
}

pub struct Prepared(PreparedCompactAnalysis);

impl Prepared {
    /// Run a resolved batch against an options-only view, on the view's pool.
    pub fn run(self, view: &Catalog) -> Result<String, String> {
        (self.0)(&view.inner)
    }
}

impl Catalog {
    pub fn new(
        dialect: String,
        quoted_ignore_case: bool,
        known_functions: Vec<String>,
        known_types: Vec<String>,
        initial: Relations,
    ) -> Result<Self, String> {
        Ok(Self {
            inner: ProjectCatalog::poc_new(CatalogInput {
                dialect,
                quoted_ignore_case,
                known_functions,
                known_types,
                relations: relations(initial),
            })?,
        })
    }

    pub fn update_relations(&mut self, value: Relations) {
        self.inner.poc_update_relations(relations(value));
    }

    pub fn update_analysis(&mut self, value: Vec<(String, (Cols, Cols))>) {
        self.inner.poc_update_analysis(
            value
                .into_iter()
                .map(|(name, (types, nullability))| (name, (Columns(types), Columns(nullability))))
                .collect(),
        );
    }

    pub fn register_override(&mut self, value: Relations) -> usize {
        self.inner.poc_register_override(relations(value))
    }

    pub fn with_relations(&self, value: Relations) -> Self {
        Self {
            inner: self.inner.poc_with_relations(relations(value)),
        }
    }

    pub fn set_pool(&self, pool: Arc<rayon::ThreadPool>) {
        self.inner.poc_set_pool(pool);
    }

    /// Options-only view that shares this catalog's pool and function probes.
    pub fn view(&self) -> Self {
        Self {
            inner: self.inner.analysis_view(),
        }
    }

    /// Resolve a compact batch payload against the current catalog state (`prepare_compact`).
    pub fn prepare_compact(&self, payload: &str) -> Result<Prepared, String> {
        crate::query_analysis::main::prepare_project_catalog::prepare_project_compact_with_catalog(
            payload,
            &self.inner,
        )
        .map(Prepared)
    }

    /// `binding_results` on the caller's current rayon pool.
    pub fn binding_results(
        &self,
        requests: Vec<BindingRequest>,
    ) -> Result<Vec<Vec<DiagnosticRow>>, String> {
        self.inner.poc_binding_results(
            requests
                .into_iter()
                .map(|(sql, references, overrides)| (sql, references, relations(overrides)))
                .collect(),
        )
    }
}

/// `normalize_analysis_sqls`, sequentially on the calling thread.
pub fn normalize_analysis_sql(
    dialect: &str,
    request: NormalizationRequest,
) -> Result<String, String> {
    crate::semantic_validation::main::normalize_batch::normalize_analysis_sqls(
        dialect,
        vec![request],
        None,
    )
    .pop()
    .unwrap_or_else(|| Err("no result".to_owned()))
}

/// Module-level `analyze_project_queries_compact_json` (no catalog).
pub fn analyze_project_compact_json(request_json: &str) -> Result<String, String> {
    crate::query_analysis::main::analyze_project_compact::analyze_project_compact_json(request_json)
}

/// Authored MODEL/CONSTANT/ENUM header value (mirror of the crate-internal type).
#[derive(Clone, Debug, PartialEq)]
pub enum HeaderValue {
    Null,
    Boolean(bool),
    BareWord(String),
    String(String),
    List(Vec<HeaderValue>),
    Map(Vec<(String, HeaderValue)>),
    Set(Vec<HeaderValue>),
    Tuple(Vec<HeaderValue>),
    TypedConstant(Vec<(String, HeaderValue)>),
    Hook(String),
}

fn header_value(value: crate::compiler::models::AuthoredValue) -> HeaderValue {
    use crate::compiler::models::AuthoredValue as A;
    let map = |pairs: Vec<(String, A)>| {
        pairs
            .into_iter()
            .map(|(key, value)| (key, header_value(value)))
            .collect()
    };
    match value {
        A::Null => HeaderValue::Null,
        A::Boolean(value) => HeaderValue::Boolean(value),
        A::BareWord(value) => HeaderValue::BareWord(value),
        A::String(value) => HeaderValue::String(value),
        A::List(values) => HeaderValue::List(values.into_iter().map(header_value).collect()),
        A::Set(values) => HeaderValue::Set(values.into_iter().map(header_value).collect()),
        A::Tuple(values) => HeaderValue::Tuple(values.into_iter().map(header_value).collect()),
        A::Map(pairs) => HeaderValue::Map(map(pairs)),
        A::TypedConstant(pairs) => HeaderValue::TypedConstant(map(pairs)),
        A::InlineSqlHook(sql) => HeaderValue::Hook(sql),
        A::NamedSqlHook(name, _) | A::PythonHook(name, _) => HeaderValue::Hook(name),
    }
}

/// Byte offsets (header start, header end, SQL start) of a leading `MODEL (...);` header.
pub fn match_model_header(text: &str) -> Option<(usize, usize, usize)> {
    let (start, end, sql) = crate::compiler::_helpers::model_headers::matching::match_one(text)?;
    let mut offsets = [start, end, sql];
    let mut found = [None; 3];
    for (count, (byte, _)) in text.char_indices().chain([(text.len(), ' ')]).enumerate() {
        for (slot, offset) in offsets.iter_mut().enumerate() {
            if found[slot].is_none() && *offset == count {
                found[slot] = Some(byte);
                *offset = usize::MAX;
            }
        }
    }
    Some((found[0]?, found[1]?, found[2]?))
}

/// Parse the body of a MODEL/CONSTANT/ENUM header (the text between its parentheses).
pub fn parse_header(body: &str) -> Result<HeaderValue, String> {
    crate::compiler::_helpers::model_headers::tokenization::parse_one(body).map(header_value)
}

/// Native conservative `@@name` substitution: (status, substituted SQL); status 2 = fallback.
pub fn substitute_vars(sql: &str, variables: &[(String, String)]) -> (u8, Option<String>) {
    crate::compiler::main::sql_interpolation::substitute_batch(&[sql.to_owned()], variables)
        .pop()
        .unwrap_or((2, None))
}

/// Native logical reference extraction: (kind, name, package) or None when unsupported.
pub fn extract_references(sql: &str) -> Option<Vec<(String, String, Option<String>)>> {
    crate::compiler::main::sql_references::extract(sql).map(|references| {
        references
            .into_iter()
            .map(|(kind, name, package, _)| (kind, name, package))
            .collect()
    })
}
