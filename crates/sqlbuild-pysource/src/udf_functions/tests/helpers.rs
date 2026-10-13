use crate::udf_functions::models::UdfKeyword;

/// A `@udf(...)` keyword fact.
pub(super) fn keyword(name: Option<&str>, line: usize) -> UdfKeyword {
    UdfKeyword {
        name: name.map(str::to_owned),
        line,
    }
}
