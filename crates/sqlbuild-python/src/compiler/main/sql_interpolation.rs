//! Public compiler entry point for conservative scalar SQL interpolation.

pub(crate) fn substitute_batch(
    sqls: &[String],
    variables: &[(String, String)],
) -> Vec<(u8, Option<String>)> {
    crate::compiler::_helpers::sql_interpolation::substitution::substitute_batch(sqls, variables)
}
