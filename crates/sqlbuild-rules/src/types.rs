/// Answers type equality the native type system cannot normalize.
pub type TypeEquality<'a> = dyn FnMut(&str, &str) -> Result<bool, String> + 'a;
