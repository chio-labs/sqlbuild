use crate::type_system::models::{PythonInteger, TypeNormalization};

pub(super) fn normalization_text(normalization: &TypeNormalization) -> String {
    let optional =
        |value: &Option<PythonInteger>| value.as_ref().map_or("-".to_owned(), ToString::to_string);
    let normalized = &normalization.normalized;
    format!(
        "{} | {} | {} | {} | {} | {}",
        normalized.normalized_name,
        normalized.family.as_str(),
        optional(&normalized.precision),
        optional(&normalized.scale),
        optional(&normalized.length),
        normalization.parse_error.as_deref().unwrap_or("-"),
    )
}
