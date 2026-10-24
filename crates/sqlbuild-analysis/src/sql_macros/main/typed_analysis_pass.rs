use crate::semantic_validation::models::Expansion;
use crate::sql_macros::_helpers::typing::typed_calls::{markable_calls, typed_sql};
use crate::sql_macros::models::TypedCall;

/// `sql` with its typed calls marked and the pass mapping offsets back, if any call is marked.
#[must_use]
pub fn typed_analysis_pass(
    sql: &str,
    calls: &[TypedCall],
    dialect: &str,
) -> Option<(String, Vec<Expansion>)> {
    let (typed, insertions) = typed_sql(sql, &markable_calls(sql, calls, dialect));
    if insertions.is_empty() {
        return None;
    }
    let mut counted: ((usize, usize), (usize, usize)) = ((0, 0), (0, 0));
    let characters = |text: &str, (byte, count): &mut (usize, usize), to: usize| {
        *count += text[*byte..to].chars().count();
        *byte = to;
        *count
    };
    let mut pass: Vec<Expansion> = Vec::with_capacity(insertions.len());
    for insertion in &insertions {
        let source: usize = characters(sql, &mut counted.0, insertion.source.0);
        let output_start: usize = characters(&typed, &mut counted.1, insertion.output.0);
        let output_end: usize = characters(&typed, &mut counted.1, insertion.output.1);
        pass.push(Expansion {
            source_start: source,
            source_end: source,
            output_start,
            output_end,
        });
    }
    Some((typed, pass))
}
