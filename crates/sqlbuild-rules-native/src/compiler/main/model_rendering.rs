//! Public compiler entry point for parallel native model rendering facts.

use crate::compiler::_helpers::model_rendering::batch::{ModelRenderFacts, render_batch};
use crate::compiler::_helpers::model_rendering::syntax::parse_lexical_syntax;

pub(crate) fn render_models(
    sqls: &[Option<String>],
    syntax_json: &str,
) -> Result<Vec<ModelRenderFacts>, String> {
    render_batch(sqls, &parse_lexical_syntax(syntax_json)?)
}
