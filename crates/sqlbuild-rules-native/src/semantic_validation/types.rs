use crate::semantic_validation::models::Columns;
use std::collections::HashMap;

pub(crate) type Relations = HashMap<String, Columns>;
pub(crate) type BindingRequest = (String, Vec<(String, bool)>, Relations);
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
