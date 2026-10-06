use crate::semantic_validation::models::{Columns, ProjectCatalog};
use std::collections::HashMap;

pub(crate) type Relations = HashMap<String, Columns>;
pub(crate) type BindingRequest = (String, Vec<(String, bool)>, Relations);
/// One analysis SQL with its relation stubs and placeholder defaults.
pub(crate) type NormalizationRequest = (String, HashMap<String, String>, HashMap<String, String>);
pub(crate) type DiagnosticRow = (
    String,
    String,
    Option<usize>,
    Option<usize>,
    Option<usize>,
    Option<usize>,
    String,
);
pub(crate) type Expansion = (usize, usize, usize, usize);
pub(crate) type ProbeKey = (polyglot_sql::DialectType, String, usize);
/// Compact analysis whose catalog schemas are resolved; it runs with an options-only catalog.
pub(crate) type PreparedCompactAnalysis =
    Box<dyn FnOnce(&ProjectCatalog) -> Result<String, String> + Send>;
