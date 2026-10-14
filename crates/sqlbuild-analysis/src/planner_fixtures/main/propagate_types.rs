//! Ordered direct-lineage fixture type propagation.

use std::collections::BTreeSet;

use crate::planner_fixtures::models::{FixtureTypeModel, FixtureTypeRead, FixtureTypeState};

/// Infer a missing output type only when known upstream types agree exactly.
pub fn propagate_types(
    mut state: FixtureTypeState,
    models: &[FixtureTypeModel],
) -> FixtureTypeState {
    for model in models {
        for projection in &model.projections {
            let upstream_types: BTreeSet<String> = projection
                .upstream
                .iter()
                .filter_map(|read| state.known.get(&read.key)?.get(&read.column).cloned())
                .collect();
            if upstream_types.len() != 1 {
                continue;
            }
            let Some(sql_type) = upstream_types.into_iter().next() else {
                continue;
            };
            let model_types = state.known.entry(model.key.clone()).or_default();
            if !model_types.contains_key(&projection.output_column) {
                model_types.insert(projection.output_column.clone(), sql_type.clone());
                state.additions.push((
                    FixtureTypeRead {
                        key: model.key.clone(),
                        column: projection.output_column.clone(),
                    },
                    sql_type,
                ));
            }
        }
    }
    state
}
