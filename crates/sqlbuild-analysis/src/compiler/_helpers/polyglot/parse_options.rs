//! The Polyglot parse options SQLBuild's wheel proxy applies to every parse.

use polyglot_sql::{ComplexityGuardOptions, ParseOptions};

use crate::lineage::constants::MAX_FUNCTION_CALL_DEPTH;

/// The proxy's complexity guard, decoded as the wheel decodes it.
pub(crate) fn guarded_parse_options() -> Result<ParseOptions, serde_json::Error> {
    let guard: ComplexityGuardOptions = serde_json::from_value(serde_json::json!({
        "maxFunctionCallDepth": MAX_FUNCTION_CALL_DEPTH,
    }))?;
    Ok(ParseOptions {
        complexity_guard: Some(guard),
    })
}
