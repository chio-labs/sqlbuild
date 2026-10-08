//! Active `@param("name")` references in one SQL test case.

/// One reference by Python code-point offsets: `sql[start:end]` is replaced by `name`'s value.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParameterReference {
    pub start: usize,
    pub end: usize,
    pub name: String,
}
