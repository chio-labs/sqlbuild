//! `get_validated_model_cursor_intrinsics`: check and canonicalize one model query's intrinsics.

use crate::cursor_intrinsics::_helpers::reserved::reserved_function_error;
use crate::cursor_intrinsics::main::replace_intrinsics::replace_intrinsics;
use crate::cursor_intrinsics::models::IntrinsicModel;

/// The query with every intrinsic call written `name()`, or why the model may not use them.
pub fn validated_model_intrinsics(
    sql: &str,
    reserved_markers: &[String],
    model: &IntrinsicModel<'_>,
) -> Result<String, String> {
    let context: String = format!("Model '{}'", model.name);
    if reserved_markers
        .iter()
        .any(|marker| sql.contains(marker.as_str()))
    {
        return Err(format!(
            "{context} contains a reserved internal cursor marker"
        ));
    }
    if let Some(message) = reserved_function_error(sql, &context) {
        return Err(message);
    }
    let (canonical, found) = replace_intrinsics(sql, &context, |name| format!("{name}()"))?;
    if !found {
        return Ok(canonical);
    }
    if !model.incremental {
        return Err(format!(
            "{context} uses cursor intrinsics but is not a built-in incremental model"
        ));
    }
    if model
        .cursor
        .is_none_or(|cursor| str::trim(cursor).is_empty())
    {
        return Err(format!(
            "{context} uses cursor intrinsics but does not declare a cursor"
        ));
    }
    Ok(canonical)
}
