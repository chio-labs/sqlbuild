//! Parallel native rendering facts for every model in one compile.

use rayon::iter::{IntoParallelRefIterator, ParallelIterator};

use crate::compiler::_helpers::model_rendering::declaration_scan::declaration_reference_starts;
use crate::compiler::_helpers::sql_references::extraction::{
    StaticReference, extract, extract_with_syntax,
};
use crate::sql_scan::models::LexicalSyntax;

const RENDER_WORKERS: usize = 4;

/// Declaration offsets in code points and references for one model; `None` defers to Python.
pub(crate) type ModelRenderFacts = (Option<Vec<usize>>, Option<Vec<StaticReference>>);

/// Scan every model in parallel; `None` inputs are models Python renders entirely.
pub(crate) fn render_batch(
    sqls: &[Option<String>],
    syntax: &LexicalSyntax,
) -> Result<Vec<ModelRenderFacts>, String> {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(RENDER_WORKERS.min(sqls.len().max(1)))
        .thread_name(|index| format!("sqlbuild-render-{index}"))
        .build()
        .map_err(|error| error.to_string())?;
    Ok(pool.install(|| {
        sqls.par_iter()
            .map(|sql| {
                sql.as_deref()
                    .map_or((None, None), |sql| render_one(sql, syntax))
            })
            .collect()
    }))
}

fn render_one(sql: &str, syntax: &LexicalSyntax) -> ModelRenderFacts {
    let starts = declaration_reference_starts(sql);
    let references = if sql.as_bytes().contains(&b'@') {
        None
    } else {
        sql_references(sql, syntax)
    };
    (
        starts.map(|starts| code_point_offsets(sql, starts)),
        references,
    )
}

fn code_point_offsets(sql: &str, byte_offsets: Vec<usize>) -> Vec<usize> {
    if sql.is_ascii() {
        return byte_offsets;
    }
    byte_offsets
        .into_iter()
        .map(|offset| sql[..offset].chars().count())
        .collect()
}

/// Return the references Python's extractor would find, or `None` where Python must decide.
pub(crate) fn sql_references(sql: &str, syntax: &LexicalSyntax) -> Option<Vec<StaticReference>> {
    if syntax.reads_differently_from_generic(sql) {
        extract_with_syntax(sql, syntax)
    } else {
        extract(sql)
    }
}
