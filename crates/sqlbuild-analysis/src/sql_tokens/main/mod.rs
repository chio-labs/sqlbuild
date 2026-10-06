#[cfg(any(test, feature = "test-support"))]
pub mod builtin_function_names;
pub mod canonical_tokens;
pub mod case_folding;
pub mod is_unquoted_word;
pub mod name_positions;
pub mod projection_spans;
pub mod query_fingerprint;
pub mod token_texts;
